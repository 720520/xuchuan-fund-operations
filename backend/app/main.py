import hashlib
import os
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError

from . import schemas as S
from .config import Settings
from .db import connect, now, uid
from .mailbox_security import encrypt_password, stored_config, test_connection
from .models import (
    AuditEvent,
    Document,
    EffectiveNav,
    ExceptionTask,
    LoginAttempt,
    Mailbox,
    Manager,
    Membership,
    NavRecord,
    ParseJob,
    Product,
    ProductFiling,
    ProductGrant,
    Session,
    ShareClass,
    User,
    ValidationRule,
)
from .security import (
    OPERATORS,
    ROLES,
    audit,
    digest,
    new_session,
    password_hash,
    require,
    rights,
    session_user,
    verify_password,
)
from .services import (
    add_nav,
    archive,
    change_product_lifecycle,
    performance,
    refresh_missing,
    select_effective,
)


def row(value, omit=()):
    if value is None:
        return None
    result = {}
    for column in value.__table__.columns:
        if column.name in omit:
            continue
        v = getattr(value, column.name)
        result[column.name] = str(v) if isinstance(v, Decimal) else v
    return result


def create_app(settings=None):
    settings = settings or Settings()
    app = FastAPI(
        title="序川 · 基金运营", version="0.1.0", docs_url=None, redoc_url=None
    )
    engine, factory = connect(settings.database_url)
    app.state.settings, app.state.engine, app.state.factory = settings, engine, factory
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT"],
        allow_headers=["Content-Type"],
    )

    @app.middleware("http")
    async def boundaries(request, call_next):
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            if request.headers.get("origin") not in settings.origins:
                return JSONResponse({"detail": "请求来源不可信"}, status_code=403)
            try:
                size = int(request.headers.get("content-length", "0"))
            except ValueError:
                return JSONResponse({"detail": "无效请求长度"}, status_code=400)
            if size > settings.max_upload + 1024 * 1024:
                return JSONResponse({"detail": "请求超过上传限制"}, status_code=413)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Cache-Control"] = (
            "no-store" if request.url.path.startswith("/api") else "no-cache"
        )
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; object-src 'none'"
        )
        return response

    @app.exception_handler(IntegrityError)
    async def integrity_error(request, exc):
        return JSONResponse(
            {"detail": "记录冲突或关联无效，请刷新后重试"}, status_code=409
        )

    def db():
        with factory() as session:
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise

    def user(request: Request, session=Depends(db, scope="function")):
        return session_user(session, request.cookies.get("xuchuan_session"))

    def manager_permission(session, actor, manager_id):
        p = rights(session, actor, manager_id)
        if not (p["read"] or p["admin"]):
            raise HTTPException(403, "没有该牌照的访问权限")
        return p

    def product_query(session, actor, manager_id):
        p = manager_permission(session, actor, manager_id)
        if p["all_products"] and not p["archive"]:
            record_cross_read(session, actor, manager_id)
        q = select(Product).where(Product.manager_id == manager_id)
        if not p["all_products"]:
            q = q.where(
                Product.id.in_(
                    select(ProductGrant.product_id).where(
                        ProductGrant.user_id == actor.id
                    )
                )
            )
        return q

    def get_product(session, actor, product_id, action="read"):
        p = session.get(Product, product_id)
        if not p:
            raise HTTPException(404, "产品不存在")
        require(session, actor, p.manager_id, action, p.id)
        if action == "read" and not rights(session, actor, p.manager_id)["archive"]:
            record_cross_read(session, actor, p.manager_id)
        return p

    def record_cross_read(session, actor, manager_id):
        if session.scalar(
            select(Membership.id).where(
                Membership.user_id == actor.id, Membership.manager_id == manager_id
            )
        ):
            return
        since = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
        if not session.scalar(
            select(AuditEvent.id)
            .where(
                AuditEvent.actor_id == actor.id,
                AuditEvent.manager_id == manager_id,
                AuditEvent.action == "manager.cross_read",
                AuditEvent.created_at >= since,
            )
            .limit(1)
        ):
            audit(
                session,
                actor,
                manager_id,
                "manager.cross_read",
                manager_id,
                {"scope": "product_details", "coalesced_window_minutes": 30},
            )

    def get_document(session, actor, document_id):
        doc = session.get(Document, document_id)
        if not doc:
            raise HTTPException(404, "原件不存在")
        permissions = rights(session, actor, doc.manager_id)
        # Mixed-product attachments must not be leaked through a single product grant.
        if not permissions["archive"]:
            raise HTTPException(403, "原始附件可能含其他产品，须具有牌照全产品查看权限")
        require(session, actor, doc.manager_id)
        return doc

    def get_issue(session, actor, issue_id):
        issue = session.get(ExceptionTask, issue_id)
        if not issue:
            raise HTTPException(404, "待办不存在")
        require(session, actor, issue.manager_id, "member")
        return issue

    def issue_row(session, issue):
        item = row(issue)
        item["product_name"] = (
            session.get(Product, issue.product_id).name
            if issue.product_id
            else "待识别产品"
        )
        item["assignee_name"] = (
            session.get(User, issue.assignee_id).name if issue.assignee_id else None
        )
        item["candidates"] = [
            row(r)
            for r in session.scalars(
                select(NavRecord)
                .where(
                    NavRecord.manager_id == issue.manager_id,
                    NavRecord.id.in_(issue.payload.get("record_ids", [])),
                )
                .order_by(NavRecord.received_at)
            )
        ]
        return item

    def nav_from_input(
        session, actor, manager_id, data, document=None, row_key=None, action="write"
    ):
        p = get_product(session, actor, data.product_id, action)
        if p.lifecycle_status in {"liquidated", "archived"}:
            raise HTTPException(422, "已清算或已归档产品不可人工补录净值；恢复运作后方可操作")
        s = session.get(ShareClass, data.share_id)
        if (
            p.manager_id != manager_id
            or not s
            or s.product_id != p.id
            or s.manager_id != manager_id
        ):
            raise HTTPException(422, "产品、份额与牌照不一致")
        try:
            return add_nav(
                session,
                manager_id,
                p,
                s,
                data.model_dump(mode="json"),
                actor,
                document,
                row_key,
                manual=True,
            )
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get("/api/health")
    def health(session=Depends(db, scope="function")):
        session.execute(select(1))
        return {"status": "ok", "version": "0.1.0"}

    @app.post("/api/auth/login")
    def login(data: S.Login, response: Response, session=Depends(db, scope="function")):
        email = data.email.strip().lower()
        key = digest(email)
        # Row lock makes the persistent counter safe across API workers.
        attempt = session.scalar(
            select(LoginAttempt).where(LoginAttempt.key == key).with_for_update()
        )
        if attempt and attempt.blocked_until and attempt.blocked_until > now():
            raise HTTPException(429, "尝试次数过多，请 15 分钟后重试")
        actor = session.scalar(select(User).where(User.email == email))
        valid = (
            actor
            and actor.active
            and verify_password(actor.password_hash, data.password)
        )
        if not valid:
            # A dummy Argon2 verification prevents cheap account enumeration.
            if not actor:
                verify_password(app.state.dummy_hash, data.password)
            if not attempt:
                attempt = LoginAttempt(key=key, failures=0)
                session.add(attempt)
            if attempt.blocked_until and attempt.blocked_until <= now():
                attempt.failures = 0
            attempt.failures += 1
            if attempt.failures >= 5:
                attempt.blocked_until = (
                    datetime.now(timezone.utc) + timedelta(minutes=15)
                ).isoformat()
            session.commit()  # Failed authentication still persists its throttle.
            raise HTTPException(401, "账号或密码错误")
        if attempt:
            session.delete(attempt)
        token = new_session(session, actor.id, settings.session_hours)
        response.set_cookie(
            "xuchuan_session",
            token,
            httponly=True,
            secure=settings.cookie_secure,
            samesite="strict",
            max_age=settings.session_hours * 3600,
            path="/",
        )
        for member in session.scalars(
            select(Membership).where(Membership.user_id == actor.id)
        ):
            audit(session, actor, member.manager_id, "auth.login", actor.id)
        return {"id": actor.id, "name": actor.name, "email": actor.email}

    app.state.dummy_hash = password_hash("not-an-account-password")

    @app.post("/api/auth/logout")
    def logout(
        request: Request,
        response: Response,
        actor=Depends(user),
        session=Depends(db, scope="function"),
    ):
        session.execute(
            delete(Session).where(
                Session.token_hash == digest(request.cookies["xuchuan_session"])
            )
        )
        response.delete_cookie("xuchuan_session", path="/")
        return {"ok": True}

    @app.get("/api/auth/me")
    def me(actor=Depends(user), session=Depends(db, scope="function")):
        managers = []
        for m in session.scalars(select(Manager).order_by(Manager.name)):
            p = rights(session, actor, m.id)
            if p["member"] or p["read"] or p["admin"]:
                managers.append({**row(m), "permissions": p})
        return {
            "id": actor.id,
            "name": actor.name,
            "email": actor.email,
            "managers": managers,
        }

    @app.post("/api/auth/password")
    def change_password(
        data: S.PasswordChange,
        actor=Depends(user),
        session=Depends(db, scope="function"),
    ):
        if not verify_password(actor.password_hash, data.old_password):
            raise HTTPException(422, "当前密码不正确")
        actor.password_hash = password_hash(data.new_password)
        session.execute(delete(Session).where(Session.user_id == actor.id))
        return {"ok": True, "message": "所有会话已失效，请重新登录"}

    @app.get("/api/managers/{manager_id}/products")
    def products(
        manager_id: str,
        include_hidden: bool = False,
        actor=Depends(user),
        session=Depends(db, scope="function"),
    ):
        result = []
        query = product_query(session, actor, manager_id)
        if not include_hidden:
            query = query.where(
                Product.lifecycle_status.notin_(["liquidated", "archived"])
            )
        for p in session.scalars(
            query.order_by(Product.created_at.desc())
        ):
            shares = []
            for s in session.scalars(
                select(ShareClass).where(ShareClass.product_id == p.id)
            ):
                latest = session.scalar(
                    select(EffectiveNav)
                    .where(EffectiveNav.share_id == s.id)
                    .order_by(EffectiveNav.valuation_date.desc())
                    .limit(1)
                )
                shares.append(
                    {
                        **row(s),
                        "latest": {
                            **row(session.get(NavRecord, latest.record_id)),
                            "reversal": latest.reversal,
                        }
                        if latest
                        else None,
                    }
                )
            result.append({**row(p), "shares": shares})
        return result

    def build_product(session, manager_id, data):
        p = Product(manager_id=manager_id, **data.model_dump(exclude={"shares"}))
        session.add(p)
        session.flush()
        for name in data.shares:
            session.add(ShareClass(manager_id=manager_id, product_id=p.id, name=name))
        return p

    @app.post("/api/managers/{manager_id}/products", status_code=201)
    def create_product(
        manager_id: str,
        data: S.ProductCreate,
        actor=Depends(user),
        session=Depends(db, scope="function"),
    ):
        require(session, actor, manager_id, "write")
        p = build_product(session, manager_id, data)
        audit(session, actor, manager_id, "product.created", p.id, data.model_dump())
        return row(p)

    @app.get("/api/managers/{manager_id}/product-filings")
    def product_filings(
        manager_id: str, actor=Depends(user), session=Depends(db, scope="function")
    ):
        require(session, actor, manager_id, "member")
        return [
            row(filing)
            for filing in session.scalars(
                select(ProductFiling)
                .where(ProductFiling.manager_id == manager_id)
                .order_by(ProductFiling.created_at.desc())
            )
        ]

    @app.post("/api/managers/{manager_id}/product-filings", status_code=201)
    def create_product_filing(
        manager_id: str,
        data: S.ProductCreate,
        actor=Depends(user),
        session=Depends(db, scope="function"),
    ):
        require(session, actor, manager_id, "write")
        filing = ProductFiling(
            manager_id=manager_id,
            created_by=actor.id,
            **data.model_dump(),
        )
        session.add(filing)
        session.flush()
        audit(
            session,
            actor,
            manager_id,
            "product_filing.created",
            filing.id,
            data.model_dump(),
        )
        return row(filing)

    @app.post("/api/product-filings/{filing_id}/complete")
    def complete_product_filing(
        filing_id: str, actor=Depends(user), session=Depends(db, scope="function")
    ):
        filing = session.scalar(
            select(ProductFiling).where(ProductFiling.id == filing_id).with_for_update()
        )
        if not filing:
            raise HTTPException(404, "备案记录不存在")
        require(session, actor, filing.manager_id, "write")
        if filing.status != "in_progress":
            raise HTTPException(409, "备案记录已经结束")
        data = S.ProductCreate(
            code=filing.code,
            name=filing.name,
            currency=filing.currency,
            strategy=filing.strategy,
            shares=filing.shares,
        )
        product = build_product(session, filing.manager_id, data)
        filing.status = "completed"
        filing.product_id = product.id
        filing.completed_at = now()
        audit(
            session,
            actor,
            filing.manager_id,
            "product_filing.completed",
            filing.id,
            {"product_id": product.id},
        )
        return {"ok": True, "product_id": product.id}

    @app.get("/api/managers/{manager_id}/product-settings")
    def product_settings(
        manager_id: str, actor=Depends(user), session=Depends(db, scope="function")
    ):
        require(session, actor, manager_id, "admin")
        return [
            {
                **row(p),
                "shares": [
                    {**row(s), "latest": None}
                    for s in session.scalars(
                        select(ShareClass).where(ShareClass.product_id == p.id)
                    )
                ],
            }
            for p in session.scalars(
                select(Product).where(Product.manager_id == manager_id)
            )
        ]

    @app.get("/api/managers/{manager_id}/rules")
    def rules(
        manager_id: str, actor=Depends(user), session=Depends(db, scope="function")
    ):
        manager_permission(session, actor, manager_id)
        rule = session.get(ValidationRule, manager_id)
        return row(rule) if rule else {"manager_id": manager_id, "max_nav_change": None}

    @app.put("/api/managers/{manager_id}/rules")
    def update_rules(
        manager_id: str,
        data: S.RuleInput,
        actor=Depends(user),
        session=Depends(db, scope="function"),
    ):
        require(session, actor, manager_id, "admin")
        value = None
        if data.max_nav_change is not None:
            try:
                value = Decimal(data.max_nav_change)
                if (
                    not value.is_finite()
                    or value <= 0
                    or value > 10
                    or value != value.quantize(Decimal("0.000001"))
                ):
                    raise ValueError()
            except (ValueError, InvalidOperation):
                raise HTTPException(
                    422, "阈值须为 (0, 10] 内最多六位小数的比率，如 0.05 表示 5%"
                )
        session.scalar(
            select(Manager).where(Manager.id == manager_id).with_for_update()
        )
        rule = session.get(ValidationRule, manager_id)
        before = row(rule)
        if not rule:
            rule = ValidationRule(manager_id=manager_id)
            session.add(rule)
        rule.max_nav_change, rule.updated_at = value, now()
        audit(
            session,
            actor,
            manager_id,
            "rules.updated",
            manager_id,
            {
                "before": before,
                "max_nav_change": str(value) if value is not None else None,
            },
        )
        return {"ok": True}

    @app.get("/api/managers/{manager_id}/summary")
    def summary(
        manager_id: str,
        valuation_date: date,
        actor=Depends(user),
        session=Depends(db, scope="function"),
    ):
        pids = list(
            session.scalars(
                product_query(session, actor, manager_id)
                .where(Product.lifecycle_status.notin_(["liquidated", "archived"]))
                .with_only_columns(Product.id)
            )
        )
        today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
        local_start = (
            datetime(
                today.year, today.month, today.day, tzinfo=ZoneInfo("Asia/Shanghai")
            )
            .astimezone(timezone.utc)
            .isoformat()
        )
        expected_shares = list(
            session.scalars(
                select(ShareClass.id)
                .join(Product, Product.id == ShareClass.product_id)
                .where(
                    Product.id.in_(pids),
                    Product.expected.is_(True),
                    Product.frequency != "off",
                )
            )
        )
        confirmed = session.scalar(
            select(func.count())
            .select_from(EffectiveNav)
            .where(
                EffectiveNav.share_id.in_(expected_shares),
                EffectiveNav.valuation_date == valuation_date.isoformat(),
            )
        )
        received = session.scalar(
            select(func.count(func.distinct(NavRecord.share_id))).where(
                NavRecord.share_id.in_(expected_shares),
                NavRecord.valuation_date == valuation_date.isoformat(),
            )
        )
        archived = (
            session.scalar(
                select(func.count())
                .select_from(Document)
                .where(Document.manager_id == manager_id)
            )
            if rights(session, actor, manager_id)["archive"]
            else None
        )
        processed_today = (
            session.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(
                    AuditEvent.manager_id == manager_id,
                    AuditEvent.created_at >= local_start,
                    AuditEvent.action.in_(
                        ["nav.received", "nav.selected", "nav.reversal"]
                    ),
                )
            )
            if rights(session, actor, manager_id)["all_products"]
            else None
        )
        return {
            "valuation_date": valuation_date.isoformat(),
            "expected": len(expected_shares),
            "received": received,
            "confirmed": confirmed,
            "archived": archived,
            "processed_today": processed_today,
            "calendar": "explicit-date",
        }

    @app.put("/api/products/{product_id}/schedule")
    def schedule(
        product_id: str,
        data: S.Schedule,
        actor=Depends(user),
        session=Depends(db, scope="function"),
    ):
        p = session.get(Product, product_id)
        if not p:
            raise HTTPException(404, "产品不存在")
        require(session, actor, p.manager_id, "admin")
        if p.lifecycle_status in {"liquidated", "archived"}:
            raise HTTPException(422, "已清算或已归档产品不能修改应收配置")
        before = {key: getattr(p, key) for key in data.model_fields_set}
        for key, value in data.model_dump().items():
            setattr(p, key, value)
        audit(
            session,
            actor,
            p.manager_id,
            "product.schedule_updated",
            p.id,
            {"before": before, "after": data.model_dump()},
        )
        return row(p)

    @app.post("/api/products/{product_id}/lifecycle")
    async def update_lifecycle(
        product_id: str,
        status: str = Form(...),
        effective_date: date | None = Form(None),
        reason: str = Form(...),
        material: UploadFile | None = File(None),
        actor=Depends(user),
        session=Depends(db, scope="function"),
    ):
        product = session.scalar(
            select(Product).where(Product.id == product_id).with_for_update()
        )
        if not product:
            raise HTTPException(404, "产品不存在")
        require(session, actor, product.manager_id, "admin")
        content = None
        filename = None
        if material:
            content = await material.read(settings.max_upload + 1)
            filename = material.filename
            await material.close()
        material_doc = change_product_lifecycle(
            session,
            settings,
            product,
            actor,
            status,
            effective_date,
            reason,
            filename,
            content,
        )
        return {
            **row(product),
            "material_document_id": material_doc.id if material_doc else None,
        }

    @app.post("/api/products/{product_id}/shares", status_code=201)
    def create_share(
        product_id: str,
        data: S.ShareCreate,
        actor=Depends(user),
        session=Depends(db, scope="function"),
    ):
        p = get_product(session, actor, product_id, "write")
        if p.lifecycle_status in {"liquidated", "archived"}:
            raise HTTPException(422, "已清算或已归档产品不能新增份额")
        s = ShareClass(manager_id=p.manager_id, product_id=p.id, name=data.name)
        session.add(s)
        session.flush()
        audit(
            session,
            actor,
            p.manager_id,
            "share.created",
            s.id,
            {"product_id": p.id, "name": s.name},
        )
        return row(s)

    @app.post("/api/managers/{manager_id}/nav", status_code=201)
    def manual_nav(
        manager_id: str,
        data: S.NavInput,
        actor=Depends(user),
        session=Depends(db, scope="function"),
    ):
        require(session, actor, manager_id, "write")
        return row(nav_from_input(session, actor, manager_id, data))

    @app.get("/api/products/{product_id}/nav")
    def nav_history(
        product_id: str,
        share_id: str,
        actor=Depends(user),
        session=Depends(db, scope="function"),
    ):
        p = get_product(session, actor, product_id)
        s = session.get(ShareClass, share_id)
        if not s or s.product_id != p.id:
            raise HTTPException(404, "份额不存在")
        records = list(
            session.scalars(
                select(NavRecord)
                .join(EffectiveNav, EffectiveNav.record_id == NavRecord.id)
                .where(NavRecord.share_id == s.id)
                .order_by(NavRecord.valuation_date)
            )
        )
        versions = []
        for r in session.scalars(
            select(NavRecord)
            .where(NavRecord.share_id == s.id)
            .order_by(NavRecord.valuation_date.desc(), NavRecord.received_at.desc())
            .limit(1000)
        ):
            e = session.get(EffectiveNav, (s.id, r.valuation_date))
            versions.append(
                {
                    **row(r),
                    "effective": bool(e and e.record_id == r.id),
                    "reversal": bool(e and e.record_id == r.id and e.reversal),
                    "actor_name": session.get(User, r.actor_id).name
                    if r.actor_id
                    else None,
                }
            )
        return {
            "effective": [row(r) for r in records],
            "versions": versions,
            "series": performance(records),
            "metric_basis": "单位净值变化 / 净值回撤，不是分红再投资总回报",
        }

    @app.post("/api/managers/{manager_id}/documents", status_code=201)
    async def upload(
        manager_id: str,
        file: UploadFile = File(...),
        product_id: str | None = Form(None),
        actor=Depends(user),
        session=Depends(db, scope="function"),
    ):
        require(session, actor, manager_id, "write")
        if product_id:
            p = get_product(session, actor, product_id, "write")
            if p.manager_id != manager_id:
                raise HTTPException(422, "产品与牌照不一致")
        content = await file.read(settings.max_upload + 1)
        await file.close()
        doc = archive(
            session,
            settings,
            manager_id,
            file.filename or "attachment.bin",
            content,
            "upload",
            actor,
            product_id,
        )
        session.add(ParseJob(manager_id=manager_id, document_id=doc.id))
        session.flush()
        # Raw evidence + durable queue are committed together, parsing is in a separate worker.
        return row(doc, {"storage_key"})

    @app.get("/api/managers/{manager_id}/documents")
    def documents(
        manager_id: str, actor=Depends(user), session=Depends(db, scope="function")
    ):
        require(session, actor, manager_id, "archive")
        result = []
        for doc in session.scalars(
            select(Document)
            .where(Document.manager_id == manager_id)
            .order_by(Document.received_at.desc())
            .limit(300)
        ):
            job = session.scalar(select(ParseJob).where(ParseJob.document_id == doc.id))
            detail = row(job)
            if detail:
                parsed = job.result or {}
                detail["result"] = {
                    "errors": parsed.get("errors", [])[:25],
                    "error_count": len(parsed.get("errors", [])),
                    "record_ids": parsed.get("record_ids", [])[:100],
                    "record_count": len(parsed.get("record_ids", [])),
                    "parser_version": parsed.get("parser_version"),
                }
            result.append({**row(doc, {"storage_key"}), "job": detail})
        return result

    @app.get("/api/documents/{document_id}/download")
    def download(
        document_id: str, actor=Depends(user), session=Depends(db, scope="function")
    ):
        doc = get_document(session, actor, document_id)
        require(session, actor, doc.manager_id, "download")
        path = settings.storage / doc.storage_key
        if not path.is_file():
            raise HTTPException(503, "归档原件暂不可用，请联系管理员")
        if hashlib.sha256(path.read_bytes()).hexdigest() != doc.sha256:
            raise HTTPException(503, "原件完整性校验失败，已阻止下载，请联系管理员")
        audit(session, actor, doc.manager_id, "document.downloaded", doc.id)
        return FileResponse(
            path,
            filename=doc.filename,
            media_type="application/octet-stream",
            content_disposition_type="attachment",
        )

    @app.post("/api/documents/{document_id}/reparse")
    def reparse(
        document_id: str, actor=Depends(user), session=Depends(db, scope="function")
    ):
        doc = session.get(Document, document_id)
        if not doc:
            raise HTTPException(404, "原件不存在")
        require(session, actor, doc.manager_id, "member")
        job = session.scalar(
            select(ParseJob).where(ParseJob.document_id == doc.id).with_for_update()
        )
        if not job:
            raise HTTPException(422, "原始邮件不直接解析，请选择附件")
        job.status, job.updated_at = "queued", now()
        audit(session, actor, doc.manager_id, "document.reparse_requested", doc.id)
        return row(job)

    @app.post("/api/documents/{document_id}/confirm-product", status_code=201)
    def confirm_document_product(
        document_id: str,
        data: S.ProductCreate,
        actor=Depends(user),
        session=Depends(db, scope="function"),
    ):
        doc = session.get(Document, document_id)
        if not doc:
            raise HTTPException(404, "原件不存在")
        require(session, actor, doc.manager_id, "write")
        job = session.scalar(
            select(ParseJob)
            .where(ParseJob.document_id == document_id)
            .with_for_update()
        )
        candidates = [
            error.get("candidate", {})
            for error in ((job.result or {}).get("errors", []) if job else [])
            if error.get("candidate")
        ]
        if not any(
            candidate.get("product_code") == data.code
            or (
                not candidate.get("product_code")
                and candidate.get("product_name") == data.name
            )
            for candidate in candidates
        ):
            raise HTTPException(409, "待确认产品已经变化，请重新解析后核对")
        product = build_product(session, doc.manager_id, data)
        job.status, job.updated_at = "queued", now()
        audit(
            session,
            actor,
            doc.manager_id,
            "product.confirmed_from_document",
            product.id,
            {"document_id": doc.id, **data.model_dump()},
        )
        return {"id": product.id, "parse_status": "queued"}

    @app.get("/api/managers/{manager_id}/tasks")
    def tasks(
        manager_id: str, actor=Depends(user), session=Depends(db, scope="function")
    ):
        require(session, actor, manager_id, "member")
        query = (
            select(ExceptionTask)
            .where(ExceptionTask.manager_id == manager_id)
            .order_by(ExceptionTask.created_at.desc())
        )
        active = list(session.scalars(query.where(ExceptionTask.status != "resolved")))
        recent = list(
            session.scalars(query.where(ExceptionTask.status == "resolved").limit(100))
        )
        # Never hide an old unresolved task merely because newer resolved tasks exist.
        return [issue_row(session, issue) for issue in active + recent]

    @app.post("/api/tasks/{issue_id}/claim")
    def claim(
        issue_id: str,
        data: S.Revision,
        actor=Depends(user),
        session=Depends(db, scope="function"),
    ):
        get_issue(session, actor, issue_id)
        raise HTTPException(410, "异常中心已改为共享处理，无需领取")

    @app.get("/api/managers/{manager_id}/handoff-tasks")
    def handoff_tasks(
        manager_id: str, actor=Depends(user), session=Depends(db, scope="function")
    ):
        require(session, actor, manager_id, "admin")
        result = []
        for issue in session.scalars(
            select(ExceptionTask)
            .where(
                ExceptionTask.manager_id == manager_id,
                ExceptionTask.status != "resolved",
            )
            .order_by(ExceptionTask.created_at.desc())
        ):
            item = row(issue, {"payload", "resolution"})
            item.update(
                {
                    "payload": {},
                    "resolution": None,
                    "candidates": [],
                    "product_name": session.get(Product, issue.product_id).name
                    if issue.product_id
                    else "待识别产品",
                    "assignee_name": session.get(User, issue.assignee_id).name
                    if issue.assignee_id
                    else None,
                }
            )
            result.append(item)
        return result

    @app.post("/api/tasks/{issue_id}/assign")
    def assign(
        issue_id: str,
        data: S.Assign,
        actor=Depends(user),
        session=Depends(db, scope="function"),
    ):
        get_issue(session, actor, issue_id)
        raise HTTPException(410, "异常中心已改为共享处理，不再转派")

    @app.post("/api/tasks/{issue_id}/resolve")
    def resolve(
        issue_id: str,
        data: S.Resolution,
        actor=Depends(user),
        session=Depends(db, scope="function"),
    ):
        issue = get_issue(session, actor, issue_id)
        if issue.kind not in {"conflict", "validation"}:
            raise HTTPException(422, "该类待办必须通过收件、解析或补录解决")
        select_effective(
            session,
            actor,
            issue,
            data.record_id,
            data.reversal,
            data.reason,
            data.revision,
        )
        return {"ok": True}

    @app.post("/api/tasks/{issue_id}/complete-material")
    def complete_material(
        issue_id: str,
        data: S.ManualCompletion,
        actor=Depends(user),
        session=Depends(db, scope="function"),
    ):
        issue = get_issue(session, actor, issue_id)
        if issue.kind not in {"parse", "validation"} or issue.status == "resolved":
            raise HTTPException(409, "该待办已解决或不支持人工补齐")
        changed = session.execute(
            update(ExceptionTask)
            .where(
                ExceptionTask.id == issue.id, ExceptionTask.revision == data.revision
            )
            .values(revision=data.revision + 1)
        ).rowcount
        if not changed:
            raise HTTPException(409, "待办已更新")
        doc = (
            session.get(Document, issue.payload.get("document_id"))
            if issue.kind == "parse"
            else None
        )
        records = []
        for i, data_row in enumerate(data.records):
            if issue.kind == "validation" and (
                data_row.share_id != issue.share_id
                or data_row.valuation_date.isoformat() != issue.valuation_date
            ):
                raise HTTPException(422, "更正须对应原份额与估值日期")
            r = nav_from_input(
                session,
                actor,
                issue.manager_id,
                data_row,
                doc,
                f"manual:{issue.id}:{data.revision}:{i}" if doc else None,
                "member",
            )
            if r.validation:
                raise HTTPException(422, "补录内容仍有校验错误，未保存")
            records.append(r.id)
        issue.status, issue.resolution, issue.updated_at = (
            "resolved",
            {
                "via": "manual_completion",
                "record_ids": records,
                "reason": data.reason,
                "complete_material": True,
            },
            now(),
        )
        if doc:
            job = session.scalar(select(ParseJob).where(ParseJob.document_id == doc.id))
            if job:
                job.status, job.updated_at = "manual_completed", now()
                job.result = {**job.result, "manual_record_ids": records}
        audit(
            session,
            actor,
            issue.manager_id,
            "exception.manual_completed",
            issue.id,
            issue.resolution,
        )
        return {"ok": True, "record_ids": records}

    @app.post("/api/managers/{manager_id}/check-missing")
    def missing(
        manager_id: str,
        valuation_date: date,
        actor=Depends(user),
        session=Depends(db, scope="function"),
    ):
        require(session, actor, manager_id, "write")
        if valuation_date > datetime.now(ZoneInfo("Asia/Shanghai")).date():
            raise HTTPException(422, "不能检查未来估值日期")
        refresh_missing(session, manager_id, on_date=valuation_date)
        audit(
            session,
            actor,
            manager_id,
            "receipt.checked",
            manager_id,
            {"valuation_date": valuation_date.isoformat()},
        )
        return {"ok": True}

    @app.get("/api/managers/{manager_id}/audit")
    def audit_trail(
        manager_id: str, actor=Depends(user), session=Depends(db, scope="function")
    ):
        p = manager_permission(session, actor, manager_id)
        if not (p["archive"] or p["admin"]):
            raise HTTPException(403, "没有牌照日志查看权限")
        events = list(
            session.scalars(
                select(AuditEvent)
                .where(AuditEvent.manager_id == manager_id)
                .order_by(AuditEvent.created_at.desc())
                .limit(500)
            )
        )
        return [
            {
                **row(e),
                "actor_name": session.get(User, e.actor_id).name
                if e.actor_id
                else "系统",
            }
            for e in events
        ]

    def save_access(session, actor, manager_id, target, data):
        if not set(data.roles) <= ROLES or len(set(data.roles)) != len(data.roles):
            raise HTTPException(422, "未知或重复角色")
        for product_id in set(data.product_ids):
            p = session.get(Product, product_id)
            if not p or p.manager_id != manager_id:
                raise HTTPException(422, "产品授权不能跨牌照")
        membership = session.scalar(
            select(Membership)
            .where(Membership.user_id == target.id, Membership.manager_id == manager_id)
            .with_for_update()
        )
        if membership and "admin" in membership.roles and "admin" not in data.roles:
            admins = [
                m
                for m in session.scalars(
                    select(Membership).where(Membership.manager_id == manager_id)
                )
                if "admin" in m.roles and session.get(User, m.user_id).active
            ]
            if len(admins) <= 1:
                raise HTTPException(422, "不能移除牌照最后一位管理员")
        before = row(membership)
        if not membership:
            membership = Membership(manager_id=manager_id, user_id=target.id)
            session.add(membership)
        membership.roles, membership.can_download = data.roles, data.can_download
        session.execute(
            delete(ProductGrant).where(
                ProductGrant.user_id == target.id,
                ProductGrant.product_id.in_(
                    select(Product.id).where(Product.manager_id == manager_id)
                ),
            )
        )
        for product_id in set(data.product_ids):
            session.add(ProductGrant(user_id=target.id, product_id=product_id))
        audit(
            session,
            actor,
            manager_id,
            "membership.updated",
            target.id,
            {"before": before, "after": data.model_dump(exclude={"password"})},
        )

    @app.get("/api/managers/{manager_id}/members")
    def members(
        manager_id: str, actor=Depends(user), session=Depends(db, scope="function")
    ):
        require(session, actor, manager_id, "admin")
        result = []
        for m in session.scalars(
            select(Membership).where(Membership.manager_id == manager_id)
        ):
            target = session.get(User, m.user_id)
            grants = list(
                session.scalars(
                    select(ProductGrant.product_id)
                    .join(Product, Product.id == ProductGrant.product_id)
                    .where(
                        ProductGrant.user_id == target.id,
                        Product.manager_id == manager_id,
                    )
                )
            )
            result.append(
                {
                    **row(m),
                    "name": target.name,
                    "email": target.email,
                    "active": target.active,
                    "product_ids": grants,
                }
            )
        return result

    @app.get("/api/managers/{manager_id}/operators")
    def operators(
        manager_id: str, actor=Depends(user), session=Depends(db, scope="function")
    ):
        p = manager_permission(session, actor, manager_id)
        if not (p["write"] or p["admin"]):
            raise HTTPException(403, "没有运营人员列表权限")
        return [
            {
                "user_id": m.user_id,
                "name": session.get(User, m.user_id).name,
                "roles": m.roles,
            }
            for m in session.scalars(
                select(Membership).where(Membership.manager_id == manager_id)
            )
            if set(m.roles) & OPERATORS and session.get(User, m.user_id).active
        ]

    @app.post("/api/managers/{manager_id}/members", status_code=201)
    def create_user(
        manager_id: str,
        data: S.UserCreate,
        actor=Depends(user),
        session=Depends(db, scope="function"),
    ):
        require(session, actor, manager_id, "admin")
        email = data.email.lower()
        if session.scalar(select(User.id).where(User.email == email)):
            raise HTTPException(
                409, "账号已存在；请由部署管理员通过 CLI 关联牌照，不会覆盖账号密码"
            )
        target = User(
            email=email, name=data.name, password_hash=password_hash(data.password)
        )
        session.add(target)
        session.flush()
        save_access(session, actor, manager_id, target, data)
        return {"id": target.id, "name": target.name}

    @app.put("/api/managers/{manager_id}/members/{user_id}")
    def set_access(
        manager_id: str,
        user_id: str,
        data: S.Access,
        actor=Depends(user),
        session=Depends(db, scope="function"),
    ):
        require(session, actor, manager_id, "admin")
        target = session.get(User, user_id)
        if not target or not session.scalar(
            select(Membership.id).where(
                Membership.manager_id == manager_id, Membership.user_id == user_id
            )
        ):
            raise HTTPException(404, "本牌照成员不存在")
        # Serialize membership edits to keep at least one administrator under concurrency.
        session.scalar(
            select(Manager).where(Manager.id == manager_id).with_for_update()
        )
        save_access(session, actor, manager_id, target, data)
        return {"ok": True}

    @app.get("/api/managers/{manager_id}/mailboxes")
    def mailboxes(
        manager_id: str, actor=Depends(user), session=Depends(db, scope="function")
    ):
        p = manager_permission(session, actor, manager_id)
        if not (p["archive"] or p["admin"]):
            raise HTTPException(403, "没有邮箱状态权限")
        return [
            {
                **row(m, {"credential_ciphertext", "env_prefix"}),
                "credential_configured": bool(
                    m.credential_ciphertext
                    or os.getenv(m.env_prefix + "_PASSWORD")
                    or os.getenv(m.env_prefix + "_OAUTH_TOKEN")
                ),
            }
            for m in session.scalars(
                select(Mailbox)
                .where(Mailbox.manager_id == manager_id)
                .order_by(Mailbox.label)
            )
        ]

    def check_mailbox_connection(config):
        try:
            return test_connection(config)
        except Exception as exc:  # noqa: BLE001 - remote errors are deliberately bounded
            raise HTTPException(
                422,
                f"连接测试失败（{type(exc).__name__}）。请检查服务器、端口、加密方式、账号、IMAP开关和客户端授权码。",
            ) from None

    def mailbox_values(data):
        return {
            "label": data.label,
            "host": data.host.lower(),
            "port": data.port,
            "tls": data.tls,
            "username": data.username.strip(),
            "since": data.since.isoformat(),
            "all_folders": data.all_folders,
            "send_id": data.send_id,
            "enabled": data.enabled,
        }

    def connection_values(values, password):
        return {
            "host": values["host"],
            "port": values["port"],
            "tls": values["tls"],
            "username": values["username"],
            "password": password,
            "send_id": values["send_id"],
        }

    @app.post("/api/managers/{manager_id}/mailboxes", status_code=201)
    def create_mailbox(
        manager_id: str,
        data: S.MailboxCreate,
        actor=Depends(user),
        session=Depends(db, scope="function"),
    ):
        require(session, actor, manager_id, "admin")
        values = mailbox_values(data)
        duplicate = session.scalar(
            select(Mailbox.id).where(
                Mailbox.manager_id == manager_id,
                Mailbox.host == values["host"],
                Mailbox.username == values["username"],
            )
        )
        if duplicate:
            raise HTTPException(409, "该牌照已登记同一邮箱账号，请编辑现有配置")
        folders = check_mailbox_connection(connection_values(values, data.password))
        box_id = uid()
        box = Mailbox(
            id=box_id,
            manager_id=manager_id,
            env_prefix="MAIL_WEB_" + box_id.replace("-", "").upper(),
            credential_ciphertext=encrypt_password(settings, box_id, data.password),
            **values,
        )
        session.add(box)
        session.flush()
        audit(
            session,
            actor,
            manager_id,
            "mailbox.created",
            box.id,
            {
                "host": box.host,
                "username": box.username,
                "all_folders": box.all_folders,
                "enabled": box.enabled,
                "folder_count": len(folders),
                "credential": "encrypted",
            },
        )
        return {"id": box.id, "folders": folders}

    @app.put("/api/managers/{manager_id}/mailboxes/{mailbox_id}")
    def update_mailbox(
        manager_id: str,
        mailbox_id: str,
        data: S.MailboxUpdate,
        actor=Depends(user),
        session=Depends(db, scope="function"),
    ):
        require(session, actor, manager_id, "admin")
        box = session.scalar(
            select(Mailbox)
            .where(Mailbox.id == mailbox_id, Mailbox.manager_id == manager_id)
            .with_for_update()
        )
        if not box:
            raise HTTPException(404, "邮箱不存在")
        values = mailbox_values(data)
        duplicate = session.scalar(
            select(Mailbox.id).where(
                Mailbox.manager_id == manager_id,
                Mailbox.host == values["host"],
                Mailbox.username == values["username"],
                Mailbox.id != box.id,
            )
        )
        if duplicate:
            raise HTTPException(409, "该牌照已登记同一邮箱账号")
        folders = []
        if data.enabled or data.password:
            password = data.password or stored_config(settings, box).get("password")
            folders = check_mailbox_connection(connection_values(values, password))
        before = {
            "host": box.host,
            "username": box.username,
            "enabled": box.enabled,
            "all_folders": box.all_folders,
        }
        for key, value in values.items():
            setattr(box, key, value)
        if data.password:
            box.credential_ciphertext = encrypt_password(
                settings, box.id, data.password
            )
        box.error = None
        audit(
            session,
            actor,
            manager_id,
            "mailbox.updated",
            box.id,
            {
                "before": before,
                "after": {
                    "host": box.host,
                    "username": box.username,
                    "enabled": box.enabled,
                    "all_folders": box.all_folders,
                },
                "credential_replaced": bool(data.password),
                "folder_count": len(folders) if folders else None,
            },
        )
        return {"ok": True, "folders": folders}

    @app.post("/api/managers/{manager_id}/mailboxes/{mailbox_id}/test")
    def test_mailbox(
        manager_id: str,
        mailbox_id: str,
        actor=Depends(user),
        session=Depends(db, scope="function"),
    ):
        require(session, actor, manager_id, "admin")
        box = session.scalar(
            select(Mailbox).where(
                Mailbox.id == mailbox_id, Mailbox.manager_id == manager_id
            )
        )
        if not box:
            raise HTTPException(404, "邮箱不存在")
        folders = check_mailbox_connection(stored_config(settings, box))
        audit(
            session,
            actor,
            manager_id,
            "mailbox.connection_tested",
            box.id,
            {"folder_count": len(folders)},
        )
        return {"ok": True, "folders": folders}

    frontend = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    if frontend.is_dir():
        app.mount("/", StaticFiles(directory=frontend, html=True), name="frontend")
    return app


app = create_app()
