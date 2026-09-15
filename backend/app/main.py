import hashlib
import os
import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from email import policy
from email.parser import BytesParser
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo

from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    Query,
    Response,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import String, cast, delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError

from . import schemas as S
from .config import Settings
from .calendar_refresh import read_status as calendar_refresh_status
from .db import connect, now, uid
from .mail_classification import (
    apply_manual_classification,
    full_message_text,
    safe_message_html,
)
from .mailbox_security import (
    encrypt_password,
    encrypt_sensitive_value,
    mask_sensitive_value,
    stored_config,
    test_connection,
)
from .nav_export import build_nav_export
from .models import (
    AuditEvent,
    Document,
    DocumentMaterial,
    DocumentMaterialInvestor,
    DocumentMaterialProduct,
    EffectiveNav,
    ExceptionTask,
    LoginAttempt,
    Investor,
    InvestorBankAccount,
    InvestorBankAccountProduct,
    InvestorProduct,
    MailAction,
    Mailbox,
    MailItem,
    MailItemProduct,
    MailReceipt,
    Manager,
    Membership,
    NavRecord,
    ParseJob,
    Product,
    ProductFiling,
    ProductGrant,
    ReceiptPolicy,
    ReceiptExpectation,
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
from .trading_calendar import (
    CalendarUnavailable,
    PUBLIC_HOLIDAY_SOURCES,
    SOURCES,
    VERSION,
    expected_on,
    is_makeup_workday,
    is_trading_day,
    month_days,
    previous_trading_day,
    public_holiday,
)
from .receipts import local_now, lock_missing, mark_resend, match_material
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
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-src 'self'; frame-ancestors 'none'; base-uri 'self'; object-src 'none'"
        )
        return response

    @app.exception_handler(CalendarUnavailable)
    async def calendar_error(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=422)

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
        material = session.get(DocumentMaterial, doc.id)
        if (
            material
            and material.sensitivity == "investor_sensitive"
            and not permissions["investor_read"]
        ):
            raise HTTPException(403, "投资者敏感资料需要单独权限")
        mail_root_id = doc.parent_id or doc.id
        if (
            not permissions["investor_read"]
            and session.scalar(
                select(MailItem.id).where(
                    MailItem.document_id == mail_root_id,
                    MailItem.category == "investor_redemption",
                )
            )
        ):
            raise HTTPException(403, "投资者业务邮件及附件需要单独权限")
        require(session, actor, doc.manager_id)
        return doc

    def document_result(doc, job=None, material=None, products=(), investors=()):
        detail = row(job)
        if detail:
            parsed = job.result or {}
            detail["result"] = {
                "errors": parsed.get("errors", [])[:25],
                "error_count": len(parsed.get("errors", [])),
                "record_ids": parsed.get("record_ids", [])[:100],
                "record_count": len(parsed.get("record_ids", [])),
                "parser_version": parsed.get("parser_version"),
                "skip_reason": parsed.get("skip_reason"),
            }
        linked = list(products)
        linked_investors = list(investors)
        return {
            **row(doc, {"storage_key"}),
            "title": material.title if material else None,
            "category": material.category if material else None,
            "material_type": material.material_type if material else None,
            "business_date": material.business_date if material else None,
            "period_start": material.period_start if material else None,
            "period_end": material.period_end if material else None,
            "notes": material.notes if material else "",
            "sensitivity": material.sensitivity if material else "standard",
            "material_status": material.status if material else "pending",
            "material_revision": material.revision if material else 0,
            "organized_at": material.confirmed_at if material else None,
            "organized_by": material.confirmed_by if material else None,
            "product_ids": [product.id for product in linked],
            "products": [{"id": product.id, "name": product.name} for product in linked],
            "investor_ids": [investor.id for investor in linked_investors],
            "investors": [
                {
                    "id": investor.id,
                    "display_name": investor.display_name,
                    "investor_type": investor.investor_type,
                }
                for investor in linked_investors
            ],
            "job": detail,
        }

    def bank_account_result(session, account):
        product_ids = list(
            session.scalars(
                select(InvestorBankAccountProduct.product_id)
                .where(InvestorBankAccountProduct.bank_account_id == account.id)
                .order_by(InvestorBankAccountProduct.product_id)
            )
        )
        return {
            **row(account, {"account_number_ciphertext"}),
            "product_ids": product_ids,
        }

    def investor_result(session, investor, products=(), material_count=0):
        return {
            **row(investor, {"certificate_number_ciphertext"}),
            "products": [
                {"id": product.id, "name": product.name} for product in products
            ],
            "product_ids": [product.id for product in products],
            "material_count": material_count,
            "bank_accounts": [
                bank_account_result(session, account)
                for account in session.scalars(
                    select(InvestorBankAccount)
                    .where(InvestorBankAccount.investor_id == investor.id)
                    .order_by(InvestorBankAccount.status, InvestorBankAccount.bank_name)
                )
            ],
        }

    def investor_source_document(session, manager_id, investor_id, document_id):
        if not document_id:
            return None
        document = session.get(Document, document_id)
        if not document or document.manager_id != manager_id:
            raise HTTPException(422, "字段来源原件不存在或不属于当前牌照")
        material = session.get(DocumentMaterial, document_id)
        if not material or material.sensitivity != "investor_sensitive":
            raise HTTPException(422, "字段来源必须是已归档的投资者敏感资料")
        linked_investor_ids = set(
            session.scalars(
                select(DocumentMaterialInvestor.investor_id).where(
                    DocumentMaterialInvestor.document_id == document_id
                )
            )
        )
        if linked_investor_ids and investor_id not in linked_investor_ids:
            raise HTTPException(422, "字段来源原件已关联其他投资者")
        if not linked_investor_ids:
            session.add(
                DocumentMaterialInvestor(
                    manager_id=manager_id,
                    document_id=document_id,
                    investor_id=investor_id,
                    created_at=now(),
                )
            )
        return document.id

    def apply_investor_profile(session, investor, data):
        investor.suitability_class = data.suitability_class
        investor.professional_investor_type = data.professional_investor_type
        investor.certificate_type = data.certificate_type
        if data.clear_certificate_number:
            investor.certificate_number_ciphertext = None
            investor.certificate_number_masked = None
        elif data.certificate_number:
            investor.certificate_number_ciphertext = encrypt_sensitive_value(
                settings,
                "investor_certificate",
                investor.id,
                data.certificate_number,
            )
            investor.certificate_number_masked = mask_sensitive_value(
                data.certificate_number
            )
        investor.certificate_valid_until = (
            data.certificate_valid_until.isoformat()
            if data.certificate_valid_until
            else None
        )
        investor.nationality_or_region = data.nationality_or_region
        investor.contact_email = data.contact_email
        investor.contact_phone = data.contact_phone
        investor.specific_object_status = data.specific_object_status
        investor.specific_object_confirmed_at = (
            data.specific_object_confirmed_at.isoformat()
            if data.specific_object_confirmed_at
            else None
        )
        investor.risk_level = data.risk_level
        investor.risk_assessed_at = (
            data.risk_assessed_at.isoformat() if data.risk_assessed_at else None
        )
        investor.risk_expires_at = (
            data.risk_expires_at.isoformat() if data.risk_expires_at else None
        )
        investor.qualified_material_status = data.qualified_material_status
        investor.qualified_material_from = (
            data.qualified_material_from.isoformat()
            if data.qualified_material_from
            else None
        )
        investor.qualified_material_until = (
            data.qualified_material_until.isoformat()
            if data.qualified_material_until
            else None
        )
        investor.profile_source_document_id = investor_source_document(
            session, investor.manager_id, investor.id, data.profile_source_document_id
        )
        investor.suitability_source_document_id = investor_source_document(
            session,
            investor.manager_id,
            investor.id,
            data.suitability_source_document_id,
        )

    def investor_products(session, manager_id, product_ids):
        products = list(
            session.scalars(
                select(Product).where(
                    Product.manager_id == manager_id,
                    Product.id.in_(product_ids),
                )
            )
        ) if product_ids else []
        if len(products) != len(product_ids):
            raise HTTPException(422, "关联产品不存在或不属于当前牌照")
        return products

    def replace_investor_products(session, actor, investor, product_ids):
        products = investor_products(session, investor.manager_id, product_ids)
        session.execute(
            delete(InvestorProduct).where(
                InvestorProduct.investor_id == investor.id
            )
        )
        timestamp = now()
        for product_id in product_ids:
            session.add(
                InvestorProduct(
                    manager_id=investor.manager_id,
                    investor_id=investor.id,
                    product_id=product_id,
                    status="confirmed",
                    created_by=actor.id,
                    created_at=timestamp,
                )
            )
        products.sort(key=lambda product: product.name)
        return products

    def replace_bank_account_products(session, account, product_ids):
        investor_products(session, account.manager_id, product_ids)
        session.execute(
            delete(InvestorBankAccountProduct).where(
                InvestorBankAccountProduct.bank_account_id == account.id
            )
        )
        timestamp = now()
        for product_id in product_ids:
            session.add(
                InvestorBankAccountProduct(
                    manager_id=account.manager_id,
                    bank_account_id=account.id,
                    product_id=product_id,
                    created_at=timestamp,
                )
            )

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

    @app.get("/api/managers/{manager_id}/receipt-policy")
    def receipt_policy(manager_id: str, actor=Depends(user), session=Depends(db, scope="function")):
        manager_permission(session, actor, manager_id)
        policy = session.get(ReceiptPolicy, manager_id)
        today = local_now().date()
        error, suggested = None, None
        try:
            suggested = previous_trading_day(today).isoformat()
            is_trading_day(today)
        except CalendarUnavailable as exc:
            error = str(exc)
        value = row(policy) if policy else {
            "enabled": False, "start_date": today.isoformat(), "followup_time": "09:00",
            "last_checked_at": None, "error": None,
        }
        return {**value, "calendar": VERSION, "calendar_sources": SOURCES,
                "calendar_error": error, "suggested_valuation_date": suggested}

    @app.put("/api/managers/{manager_id}/receipt-policy")
    def save_receipt_policy(manager_id: str, data: S.ReceiptPolicyInput,
                            actor=Depends(user), session=Depends(db, scope="function")):
        require(session, actor, manager_id, "admin")
        # Manager lock serializes first-time policy creation too.
        session.scalar(select(Manager).where(Manager.id == manager_id).with_for_update())
        policy = session.get(ReceiptPolicy, manager_id)
        today = local_now().date()
        if data.enabled:
            is_trading_day(data.start_date)
            previous_trading_day(data.start_date)
            is_trading_day(today)
        if not policy and data.start_date < today:
            raise HTTPException(422, "首次启用从今天或未来开始，不自动追补启用前的缺件")
        if policy and data.start_date.isoformat() != policy.start_date:
            raise HTTPException(422, "启用起始日已留痕，不可修改；停用或启用开关控制后续检查")
        before = row(policy)
        if not policy:
            policy = ReceiptPolicy(manager_id=manager_id, start_date=data.start_date.isoformat())
            session.add(policy)
        if data.enabled and before and not before["enabled"]:
            # A deliberate pause is not an outage: don't invent obligations during the pause.
            policy.last_scheduled_date = max(today.isoformat(), policy.start_date)
        policy.enabled, policy.followup_time = data.enabled, data.followup_time
        policy.error, policy.last_checked_at = None, None
        session.flush()
        audit(session, actor, manager_id, "receipt.policy_updated", manager_id,
              {"before": before, "after": row(policy), "calendar": VERSION})
        return row(policy)

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
        expected_products = [product.id for product in session.scalars(
            select(Product).where(Product.id.in_(pids))
        ) if expected_on(product, valuation_date)]
        expected_shares = list(session.scalars(select(ShareClass.id).where(
            ShareClass.product_id.in_(expected_products)
        )))
        confirmed = session.scalar(
            select(func.count())
            .select_from(EffectiveNav)
            .where(
                EffectiveNav.share_id.in_(expected_shares),
                EffectiveNav.valuation_date == valuation_date.isoformat(),
            )
        )
        received_shares = set(session.scalars(select(NavRecord.share_id).where(
            NavRecord.share_id.in_(expected_shares), NavRecord.valuation_date == valuation_date.isoformat(),
        )))
        received_shares.update(session.scalars(select(ReceiptExpectation.share_id).where(
            ReceiptExpectation.share_id.in_(expected_shares),
            ReceiptExpectation.valuation_date == valuation_date.isoformat(),
            ReceiptExpectation.received_at.is_not(None),
        )))
        received = len(received_shares)
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
            "calendar": VERSION,
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
        if data.frequency == "daily":
            data.cutoff = "15:00"
        before = {key: getattr(p, key) for key in data.model_fields_set}
        for key, value in data.model_dump().items():
            setattr(p, key, value)
        if not p.expected or p.frequency == "off":
            from .receipts import reconcile
            for expectation in session.scalars(select(ReceiptExpectation).where(
                ReceiptExpectation.product_id == p.id, ReceiptExpectation.cancelled.is_(False),
            )):
                reconcile(session, expectation, local_now())
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

    @app.get("/api/managers/{manager_id}/nav/export")
    def export_nav(
        manager_id: str,
        start_date: date = Query(...),
        end_date: date = Query(...),
        product_ids: list[str] | None = Query(None, alias="product_id"),
        actor=Depends(user),
        session=Depends(db, scope="function"),
    ):
        if start_date > end_date:
            raise HTTPException(422, "开始日期不能晚于结束日期")
        permissions = manager_permission(session, actor, manager_id)
        if not permissions["download"]:
            raise HTTPException(403, "没有导出净值的下载权限")

        requested = set(product_ids or [])
        accessible_products = list(session.scalars(product_query(session, actor, manager_id)))
        accessible_ids = {product.id for product in accessible_products}
        if requested and not requested.issubset(accessible_ids):
            raise HTTPException(403, "选择的产品中包含无权查看的产品")
        selected_ids = requested or accessible_ids

        records = []
        if selected_ids:
            result = session.execute(
                select(NavRecord, EffectiveNav, Product, ShareClass)
                .join(
                    EffectiveNav,
                    EffectiveNav.record_id == NavRecord.id,
                )
                .join(Product, Product.id == NavRecord.product_id)
                .join(ShareClass, ShareClass.id == NavRecord.share_id)
                .where(
                    NavRecord.manager_id == manager_id,
                    NavRecord.product_id.in_(selected_ids),
                    NavRecord.valuation_date >= start_date.isoformat(),
                    NavRecord.valuation_date <= end_date.isoformat(),
                )
                .order_by(
                    NavRecord.valuation_date,
                    Product.code,
                    Product.name,
                    ShareClass.name,
                )
                .limit(50_001)
            ).all()
            if len(result) > 50_000:
                raise HTTPException(422, "导出记录超过 50000 条，请缩小日期范围或选择单个产品")
            records = [
                {
                    "valuation_date": nav.valuation_date,
                    "product_code": product.code,
                    "product_name": product.name,
                    "share_name": share.name,
                    "currency": product.currency,
                    "unit_nav": nav.unit_nav,
                    "accumulated_nav": nav.accumulated_nav,
                    "net_assets": nav.net_assets,
                    "total_shares": nav.total_shares,
                    "source": nav.source,
                    "reversal": effective.reversal,
                    "received_at": nav.received_at,
                    "record_id": nav.id,
                    "document_id": nav.document_id,
                    "revision": effective.revision,
                }
                for nav, effective, product, share in result
            ]

        manager = session.get(Manager, manager_id)
        generated_at = datetime.now(ZoneInfo("Asia/Shanghai")).replace(tzinfo=None)
        content = build_nav_export(
            manager_name=manager.name,
            start_date=start_date,
            end_date=end_date,
            records=records,
            generated_at=generated_at,
        )
        audit(
            session,
            actor,
            manager_id,
            "nav.exported",
            manager_id,
            {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "product_ids": sorted(requested),
                "scope": "selected" if requested else "all_accessible",
                "row_count": len(records),
            },
        )
        filename = f"产品净值_{start_date:%Y%m%d}_{end_date:%Y%m%d}.xlsx"
        return Response(
            content=content,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": (
                    "attachment; filename=nav_export.xlsx; "
                    f"filename*=UTF-8''{quote(filename)}"
                )
            },
        )

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

    @app.get("/api/managers/{manager_id}/investors")
    def investors(
        manager_id: str, actor=Depends(user), session=Depends(db, scope="function")
    ):
        require(session, actor, manager_id, "investor_read")
        records = list(
            session.scalars(
                select(Investor)
                .where(Investor.manager_id == manager_id)
                .order_by(Investor.display_name, Investor.created_at)
            )
        )
        if not records:
            return []
        investor_ids = [record.id for record in records]
        products_by_investor = {investor_id: [] for investor_id in investor_ids}
        for investor_id, product in session.execute(
            select(InvestorProduct.investor_id, Product)
            .join(Product, Product.id == InvestorProduct.product_id)
            .where(InvestorProduct.investor_id.in_(investor_ids))
            .order_by(Product.name)
        ):
            products_by_investor[investor_id].append(product)
        material_counts = dict(
            session.execute(
                select(
                    DocumentMaterialInvestor.investor_id,
                    func.count(DocumentMaterialInvestor.id),
                )
                .where(DocumentMaterialInvestor.investor_id.in_(investor_ids))
                .group_by(DocumentMaterialInvestor.investor_id)
            ).all()
        )
        return [
            investor_result(
                session,
                record,
                products_by_investor[record.id],
                material_counts.get(record.id, 0),
            )
            for record in records
        ]

    @app.post("/api/managers/{manager_id}/investors", status_code=201)
    def create_investor(
        manager_id: str,
        data: S.InvestorSave,
        actor=Depends(user),
        session=Depends(db, scope="function"),
    ):
        require(session, actor, manager_id, "investor_write")
        if data.revision != 0:
            raise HTTPException(409, "新投资者记录的版本必须从零开始")
        investor_products(session, manager_id, data.product_ids)
        investor = Investor(
            manager_id=manager_id,
            investor_type=data.investor_type,
            display_name=data.display_name,
            status=data.status,
            source=data.source,
            notes=data.notes,
            created_by=actor.id,
        )
        session.add(investor)
        session.flush()
        apply_investor_profile(session, investor, data)
        products = replace_investor_products(
            session, actor, investor, data.product_ids
        )
        audit(
            session,
            actor,
            manager_id,
            "investor.created",
            investor.id,
            {
                "investor_type": investor.investor_type,
                "suitability_class": investor.suitability_class,
                "status": investor.status,
                "source": investor.source,
                "product_ids": data.product_ids,
                "certificate_number_changed": bool(data.certificate_number),
            },
        )
        return investor_result(session, investor, products, 0)

    @app.put("/api/investors/{investor_id}")
    def update_investor(
        investor_id: str,
        data: S.InvestorSave,
        actor=Depends(user),
        session=Depends(db, scope="function"),
    ):
        investor = session.scalar(
            select(Investor).where(Investor.id == investor_id).with_for_update()
        )
        if not investor:
            raise HTTPException(404, "投资者记录不存在")
        require(session, actor, investor.manager_id, "investor_write")
        if investor.revision != data.revision:
            raise HTTPException(409, "投资者信息已经变化，请刷新后重试")
        previous_product_ids = list(
            session.scalars(
                select(InvestorProduct.product_id).where(
                    InvestorProduct.investor_id == investor.id
                )
            )
        )
        before = {
            "investor_type": investor.investor_type,
            "suitability_class": investor.suitability_class,
            "specific_object_status": investor.specific_object_status,
            "qualified_material_status": investor.qualified_material_status,
            "status": investor.status,
            "source": investor.source,
            "product_ids": previous_product_ids,
            "revision": investor.revision,
        }
        investor.investor_type = data.investor_type
        investor.display_name = data.display_name
        investor.status = data.status
        investor.source = data.source
        investor.notes = data.notes
        certificate_number_changed = bool(
            data.certificate_number or data.clear_certificate_number
        )
        apply_investor_profile(session, investor, data)
        investor.updated_at = now()
        investor.revision += 1
        products = replace_investor_products(
            session, actor, investor, data.product_ids
        )
        audit(
            session,
            actor,
            investor.manager_id,
            "investor.updated",
            investor.id,
            {
                "before": before,
                "after": {
                    "investor_type": investor.investor_type,
                    "suitability_class": investor.suitability_class,
                    "specific_object_status": investor.specific_object_status,
                    "qualified_material_status": investor.qualified_material_status,
                    "status": investor.status,
                    "source": investor.source,
                    "product_ids": data.product_ids,
                    "revision": investor.revision,
                    "certificate_number_changed": certificate_number_changed,
                },
            },
        )
        return investor_result(
            session,
            investor,
            products,
            session.scalar(
                select(func.count(DocumentMaterialInvestor.id)).where(
                    DocumentMaterialInvestor.investor_id == investor.id
                )
            ),
        )

    @app.post("/api/investors/{investor_id}/bank-accounts", status_code=201)
    def create_investor_bank_account(
        investor_id: str,
        data: S.InvestorBankAccountSave,
        actor=Depends(user),
        session=Depends(db, scope="function"),
    ):
        investor = session.get(Investor, investor_id)
        if not investor:
            raise HTTPException(404, "投资者记录不存在")
        require(session, actor, investor.manager_id, "investor_write")
        if data.revision != 0:
            raise HTTPException(409, "新银行账户的版本必须从零开始")
        if not data.account_number:
            raise HTTPException(422, "新增银行账户必须填写账号")
        account_id = uid()
        account = InvestorBankAccount(
            id=account_id,
            manager_id=investor.manager_id,
            investor_id=investor.id,
            account_name=data.account_name,
            account_number_ciphertext=encrypt_sensitive_value(
                settings,
                "investor_bank_account",
                account_id,
                data.account_number,
            ),
            account_number_masked=mask_sensitive_value(data.account_number),
            bank_name=data.bank_name,
            branch_name=data.branch_name,
            currency=data.currency.upper(),
            status=data.status,
            source_document_id=investor_source_document(
                session, investor.manager_id, investor.id, data.source_document_id
            ),
            created_by=actor.id,
        )
        session.add(account)
        session.flush()
        replace_bank_account_products(session, account, data.product_ids)
        audit(
            session,
            actor,
            investor.manager_id,
            "investor.bank_account_created",
            account.id,
            {
                "investor_id": investor.id,
                "bank_name": account.bank_name,
                "currency": account.currency,
                "status": account.status,
                "product_ids": data.product_ids,
                "source_document_id": account.source_document_id,
            },
        )
        return bank_account_result(session, account)

    @app.put("/api/investor-bank-accounts/{account_id}")
    def update_investor_bank_account(
        account_id: str,
        data: S.InvestorBankAccountSave,
        actor=Depends(user),
        session=Depends(db, scope="function"),
    ):
        account = session.scalar(
            select(InvestorBankAccount)
            .where(InvestorBankAccount.id == account_id)
            .with_for_update()
        )
        if not account:
            raise HTTPException(404, "银行账户不存在")
        require(session, actor, account.manager_id, "investor_write")
        if account.revision != data.revision:
            raise HTTPException(409, "银行账户已经变化，请刷新后重试")
        before = {
            "bank_name": account.bank_name,
            "currency": account.currency,
            "status": account.status,
            "product_ids": list(
                session.scalars(
                    select(InvestorBankAccountProduct.product_id).where(
                        InvestorBankAccountProduct.bank_account_id == account.id
                    )
                )
            ),
            "revision": account.revision,
        }
        account.account_name = data.account_name
        if data.account_number:
            account.account_number_ciphertext = encrypt_sensitive_value(
                settings,
                "investor_bank_account",
                account.id,
                data.account_number,
            )
            account.account_number_masked = mask_sensitive_value(
                data.account_number
            )
        account.bank_name = data.bank_name
        account.branch_name = data.branch_name
        account.currency = data.currency.upper()
        account.status = data.status
        account.source_document_id = investor_source_document(
            session,
            account.manager_id,
            account.investor_id,
            data.source_document_id,
        )
        account.updated_at = now()
        account.revision += 1
        replace_bank_account_products(session, account, data.product_ids)
        audit(
            session,
            actor,
            account.manager_id,
            "investor.bank_account_updated",
            account.id,
            {
                "before": before,
                "after": {
                    "bank_name": account.bank_name,
                    "currency": account.currency,
                    "status": account.status,
                    "product_ids": data.product_ids,
                    "revision": account.revision,
                    "account_number_changed": bool(data.account_number),
                    "source_document_id": account.source_document_id,
                },
            },
        )
        return bank_account_result(session, account)

    @app.post("/api/managers/{manager_id}/documents", status_code=201)
    async def upload(
        manager_id: str,
        file: UploadFile = File(...),
        product_id: str | None = Form(None),
        investor_id: str | None = Form(None),
        material_scope: str | None = Form(None),
        actor=Depends(user),
        session=Depends(db, scope="function"),
    ):
        require(session, actor, manager_id, "write")
        if material_scope not in {None, "product", "investor"}:
            raise HTTPException(422, "资料目录范围不正确")
        if material_scope == "product" and not product_id:
            raise HTTPException(422, "从产品目录上传时必须指定产品")
        if material_scope == "investor" and not investor_id:
            raise HTTPException(422, "从投资者目录上传时必须指定投资者")
        if product_id:
            p = get_product(session, actor, product_id, "write")
            if p.manager_id != manager_id:
                raise HTTPException(422, "产品与牌照不一致")
        linked_investor = None
        if investor_id:
            require(session, actor, manager_id, "investor_write")
            linked_investor = session.get(Investor, investor_id)
            if not linked_investor or linked_investor.manager_id != manager_id:
                raise HTTPException(422, "投资者不存在或不属于当前牌照")
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
        job = ParseJob(manager_id=manager_id, document_id=doc.id)
        session.add(job)
        session.flush()
        if linked_investor or material_scope == "product":
            timestamp = now()
            is_investor_material = linked_investor is not None
            material = DocumentMaterial(
                document_id=doc.id,
                manager_id=manager_id,
                category="other",
                title=doc.filename,
                notes=(
                    "从投资者目录上传，资料类别待人工整理"
                    if is_investor_material
                    else "从产品目录上传，资料类别待人工整理"
                ),
                sensitivity="investor_sensitive" if is_investor_material else "standard",
                status="pending",
                confirmed_by=actor.id,
                confirmed_at=timestamp,
                created_at=timestamp,
                updated_at=timestamp,
                revision=1,
            )
            session.add(material)
            session.flush()
            if linked_investor:
                session.add(
                    DocumentMaterialInvestor(
                        manager_id=manager_id,
                        document_id=doc.id,
                        investor_id=linked_investor.id,
                        created_at=timestamp,
                    )
                )
            if product_id:
                session.add(
                    DocumentMaterialProduct(
                        manager_id=manager_id,
                        document_id=doc.id,
                        product_id=product_id,
                        created_at=timestamp,
                    )
                )
            job.status = "skipped"
            job.result = {
                "skip_reason": (
                    "投资者敏感资料已安全归档，等待人工确认资料类别"
                    if is_investor_material
                    else "产品资料已安全归档，等待人工确认资料类别"
                )
            }
            job.updated_at = timestamp
            audit(
                session,
                actor,
                manager_id,
                "document.investor_linked" if is_investor_material else "document.product_linked",
                doc.id,
                {
                    "investor_id": linked_investor.id if linked_investor else None,
                    "product_id": product_id,
                    "material_scope": material_scope or "investor",
                    "sensitivity": "investor_sensitive" if is_investor_material else "standard",
                },
            )
        # Raw evidence + durable queue are committed together, parsing is in a separate worker.
        return row(doc, {"storage_key"})

    @app.get("/api/managers/{manager_id}/documents")
    def documents(
        manager_id: str,
        paginated: bool = False,
        limit: int = 50,
        offset: int = 0,
        q: str = "",
        status: str = "all",
        product_id: str = "",
        investor_id: str = "",
        category: str = "",
        source: str = "",
        sensitivity: str = "",
        actor=Depends(user),
        session=Depends(db, scope="function"),
    ):
        permissions = require(session, actor, manager_id, "archive")
        page_result = None
        if paginated:
            if not 1 <= limit <= 100 or offset < 0:
                raise HTTPException(422, "分页参数超出允许范围")
            if status not in {"all", "pending", "linked", "attention"}:
                raise HTTPException(422, "资料状态筛选无效")
            if category not in {
                "",
                "pending",
                "nav_valuation",
                "contract",
                "investor_qualification",
                "subscription_redemption",
                "filing",
                "custody_account",
                "periodic_report",
                "risk_compliance",
                "operation_evidence",
                "other",
            }:
                raise HTTPException(422, "资料类别筛选无效")
            if sensitivity not in {"", "standard", "investor_sensitive"}:
                raise HTTPException(422, "敏感级别筛选无效")

            material_ids = select(DocumentMaterial.document_id).where(
                DocumentMaterial.manager_id == manager_id
            )
            organized_ids = select(DocumentMaterial.document_id).where(
                DocumentMaterial.manager_id == manager_id,
                DocumentMaterial.status == "organized",
            )
            sensitive_ids = select(DocumentMaterial.document_id).where(
                DocumentMaterial.manager_id == manager_id,
                DocumentMaterial.sensitivity == "investor_sensitive",
            )
            product_link_ids = select(DocumentMaterialProduct.document_id).where(
                DocumentMaterialProduct.manager_id == manager_id
            )
            investor_link_ids = select(DocumentMaterialInvestor.document_id).where(
                DocumentMaterialInvestor.manager_id == manager_id
            )
            attention_ids = select(ParseJob.document_id).where(
                ParseJob.manager_id == manager_id,
                ParseJob.status.in_({"queued", "processing", "review"}),
            )
            sensitive_mail_roots = select(MailItem.document_id).where(
                MailItem.manager_id == manager_id,
                MailItem.category == "investor_redemption",
            )
            accessible = select(Document.id).where(
                Document.manager_id == manager_id,
                ~func.lower(Document.filename).like("%.eml"),
            )
            if not permissions["investor_read"]:
                accessible = accessible.where(
                    ~Document.id.in_(sensitive_ids),
                    ~Document.id.in_(sensitive_mail_roots),
                    or_(
                        Document.parent_id.is_(None),
                        ~Document.parent_id.in_(sensitive_mail_roots),
                    ),
                )

            linked_condition = or_(
                Document.product_id.is_not(None),
                Document.id.in_(product_link_ids),
                Document.id.in_(investor_link_ids),
            )
            pending_condition = ~Document.id.in_(organized_ids)
            attention_condition = Document.id.in_(attention_ids)

            def count_documents(condition=None):
                statement = accessible
                if condition is not None:
                    statement = statement.where(condition)
                return session.scalar(
                    select(func.count()).select_from(statement.subquery())
                ) or 0

            counts = {
                "all": count_documents(),
                "pending": count_documents(pending_condition),
                "linked": count_documents(linked_condition),
                "attention": count_documents(attention_condition),
            }
            filtered = accessible
            if status == "pending":
                filtered = filtered.where(pending_condition)
            elif status == "linked":
                filtered = filtered.where(linked_condition)
            elif status == "attention":
                filtered = filtered.where(attention_condition)
            if product_id:
                filtered = filtered.where(
                    or_(
                        Document.product_id == product_id,
                        Document.id.in_(
                            select(DocumentMaterialProduct.document_id).where(
                                DocumentMaterialProduct.manager_id == manager_id,
                                DocumentMaterialProduct.product_id == product_id,
                            )
                        ),
                    )
                )
            if investor_id:
                filtered = filtered.where(
                    Document.id.in_(
                        select(DocumentMaterialInvestor.document_id).where(
                            DocumentMaterialInvestor.manager_id == manager_id,
                            DocumentMaterialInvestor.investor_id == investor_id,
                        )
                    )
                )
            if category == "pending":
                filtered = filtered.where(pending_condition)
            elif category:
                category_ids = select(DocumentMaterial.document_id).where(
                    DocumentMaterial.manager_id == manager_id,
                    DocumentMaterial.category == category,
                )
                if category == "nav_valuation":
                    completed_ids = select(ParseJob.document_id).where(
                        ParseJob.manager_id == manager_id,
                        ParseJob.status == "completed",
                    )
                    filtered = filtered.where(
                        or_(
                            Document.id.in_(category_ids),
                            Document.id.in_(completed_ids),
                        )
                    )
                elif category == "operation_evidence":
                    filtered = filtered.where(
                        or_(
                            Document.id.in_(category_ids),
                            Document.source == "lifecycle_material",
                        )
                    )
                else:
                    filtered = filtered.where(Document.id.in_(category_ids))
            if source:
                filtered = filtered.where(Document.source == source)
            if sensitivity == "investor_sensitive":
                filtered = filtered.where(Document.id.in_(sensitive_ids))
            elif sensitivity == "standard":
                filtered = filtered.where(~Document.id.in_(sensitive_ids))
            query_text = q.strip().lower()[:200]
            if query_text:
                pattern = f"%{query_text}%"
                matching_materials = select(DocumentMaterial.document_id).where(
                    DocumentMaterial.manager_id == manager_id,
                    or_(
                        func.lower(DocumentMaterial.title).like(pattern),
                        func.lower(DocumentMaterial.notes).like(pattern),
                    ),
                )
                matching_product_links = (
                    select(DocumentMaterialProduct.document_id)
                    .join(Product, Product.id == DocumentMaterialProduct.product_id)
                    .where(
                        DocumentMaterialProduct.manager_id == manager_id,
                        or_(
                            func.lower(Product.name).like(pattern),
                            func.lower(Product.code).like(pattern),
                        ),
                    )
                )
                matching_legacy_products = select(Product.id).where(
                    Product.manager_id == manager_id,
                    or_(
                        func.lower(Product.name).like(pattern),
                        func.lower(Product.code).like(pattern),
                    ),
                )
                matching_investor_links = (
                    select(DocumentMaterialInvestor.document_id)
                    .join(Investor, Investor.id == DocumentMaterialInvestor.investor_id)
                    .where(
                        DocumentMaterialInvestor.manager_id == manager_id,
                        func.lower(Investor.display_name).like(pattern),
                    )
                )
                filtered = filtered.where(
                    or_(
                        func.lower(Document.filename).like(pattern),
                        func.lower(cast(Document.metadata_json, String)).like(pattern),
                        Document.id.in_(matching_materials),
                        Document.id.in_(matching_product_links),
                        Document.product_id.in_(matching_legacy_products),
                        Document.id.in_(matching_investor_links),
                    )
                )
            total = session.scalar(
                select(func.count()).select_from(filtered.subquery())
            ) or 0
            documents = list(
                session.scalars(
                    select(Document)
                    .where(Document.id.in_(filtered))
                    .order_by(Document.received_at.desc(), Document.id.desc())
                    .offset(offset)
                    .limit(limit)
                )
            )
            page_result = {
                "total": total,
                "limit": limit,
                "offset": offset,
                "counts": counts,
            }
        else:
            documents = list(session.scalars(
                select(Document)
                .where(Document.manager_id == manager_id)
                .order_by(Document.received_at.desc())
                .limit(300)
            ))
        if not documents:
            return {**page_result, "items": []} if page_result else []
        document_ids = [doc.id for doc in documents]
        jobs = {
            job.document_id: job
            for job in session.scalars(
                select(ParseJob).where(ParseJob.document_id.in_(document_ids))
            )
        }
        materials = {
            material.document_id: material
            for material in session.scalars(
                select(DocumentMaterial).where(
                    DocumentMaterial.document_id.in_(document_ids)
                )
            )
        }
        if not permissions["investor_read"]:
            mail_root_ids = {doc.parent_id or doc.id for doc in documents}
            sensitive_mail_roots = set(
                session.scalars(
                    select(MailItem.document_id).where(
                        MailItem.manager_id == manager_id,
                        MailItem.document_id.in_(mail_root_ids),
                        MailItem.category == "investor_redemption",
                    )
                )
            )
            documents = [
                doc
                for doc in documents
                if (doc.parent_id or doc.id) not in sensitive_mail_roots
                and (
                    materials.get(doc.id) is None
                    or materials[doc.id].sensitivity != "investor_sensitive"
                )
            ]
            document_ids = [doc.id for doc in documents]
            if not documents:
                return []
        links_by_document = {}
        for link in session.scalars(
            select(DocumentMaterialProduct).where(
                DocumentMaterialProduct.document_id.in_(document_ids)
            )
        ):
            links_by_document.setdefault(link.document_id, []).append(link.product_id)
        investor_links_by_document = {}
        for link in session.scalars(
            select(DocumentMaterialInvestor).where(
                DocumentMaterialInvestor.document_id.in_(document_ids)
            )
        ):
            investor_links_by_document.setdefault(link.document_id, []).append(
                link.investor_id
            )
        referenced_product_ids = {
            product_id
            for doc in documents
            for product_id in (
                links_by_document.get(doc.id, [])
                if doc.id in materials
                else ([doc.product_id] if doc.product_id else [])
            )
        }
        product_by_id = {
            product.id: product
            for product in session.scalars(
                select(Product).where(Product.id.in_(referenced_product_ids))
            )
        } if referenced_product_ids else {}
        referenced_investor_ids = {
            investor_id
            for investor_ids in investor_links_by_document.values()
            for investor_id in investor_ids
        }
        investor_by_id = {
            investor.id: investor
            for investor in session.scalars(
                select(Investor).where(Investor.id.in_(referenced_investor_ids))
            )
        } if referenced_investor_ids else {}
        result = []
        for doc in documents:
            product_ids = (
                links_by_document.get(doc.id, [])
                if doc.id in materials
                else ([doc.product_id] if doc.product_id else [])
            )
            linked_products = sorted(
                (product_by_id[item] for item in product_ids if item in product_by_id),
                key=lambda product: product.name,
            )
            linked_investors = sorted(
                (
                    investor_by_id[item]
                    for item in investor_links_by_document.get(doc.id, [])
                    if item in investor_by_id
                ),
                key=lambda investor: investor.display_name,
            )
            result.append(
                document_result(
                    doc,
                    jobs.get(doc.id),
                    materials.get(doc.id),
                    linked_products,
                    linked_investors,
                )
            )
        return {**page_result, "items": result} if page_result else result

    @app.put("/api/documents/{document_id}/material")
    def organize_document(
        document_id: str,
        data: S.MaterialOrganization,
        actor=Depends(user),
        session=Depends(db, scope="function"),
    ):
        doc = get_document(session, actor, document_id)
        require(session, actor, doc.manager_id, "write")
        if doc.media_type == "message/rfc822" or doc.filename.lower().endswith(".eml"):
            raise HTTPException(422, "邮件正文作为通信原件保留，请整理其附件")

        product_ids = data.product_ids
        linked_products = list(
            session.scalars(
                select(Product).where(
                    Product.manager_id == doc.manager_id,
                    Product.id.in_(product_ids),
                )
            )
        ) if product_ids else []
        if len(linked_products) != len(product_ids):
            raise HTTPException(422, "关联产品不存在或不属于当前牌照")
        investor_ids = data.investor_ids
        if investor_ids or data.sensitivity == "investor_sensitive":
            require(session, actor, doc.manager_id, "investor_write")
        if investor_ids and data.sensitivity != "investor_sensitive":
            raise HTTPException(422, "关联投资者的资料必须标记为投资者敏感资料")
        if (
            data.category in {"investor_qualification", "subscription_redemption"}
            and data.sensitivity != "investor_sensitive"
        ):
            raise HTTPException(422, "投资者资料类别必须使用敏感资料权限")
        linked_investors = list(
            session.scalars(
                select(Investor).where(
                    Investor.manager_id == doc.manager_id,
                    Investor.id.in_(investor_ids),
                )
            )
        ) if investor_ids else []
        if len(linked_investors) != len(investor_ids):
            raise HTTPException(422, "关联投资者不存在或不属于当前牌照")

        material = session.scalar(
            select(DocumentMaterial)
            .where(DocumentMaterial.document_id == doc.id)
            .with_for_update()
        )
        previous_product_ids = []
        previous_investor_ids = []
        if material:
            if material.revision != data.revision:
                raise HTTPException(409, "资料整理结果已经变化，请刷新后重试")
            previous_product_ids = list(
                session.scalars(
                    select(DocumentMaterialProduct.product_id).where(
                        DocumentMaterialProduct.document_id == doc.id
                    )
                )
            )
            previous_investor_ids = list(
                session.scalars(
                    select(DocumentMaterialInvestor.investor_id).where(
                        DocumentMaterialInvestor.document_id == doc.id
                    )
                )
            )
            before = {
                "category": material.category,
                "material_type": material.material_type,
                "title": material.title,
                "business_date": material.business_date,
                "period_start": material.period_start,
                "period_end": material.period_end,
                "product_ids": previous_product_ids,
                "investor_ids": previous_investor_ids,
                "sensitivity": material.sensitivity,
                "notes": material.notes,
                "revision": material.revision,
            }
            material.revision += 1
        else:
            if data.revision != 0:
                raise HTTPException(409, "资料尚未整理，请刷新后重试")
            before = None
            material = DocumentMaterial(
                document_id=doc.id,
                manager_id=doc.manager_id,
                confirmed_by=actor.id,
                revision=1,
            )
            session.add(material)

        timestamp = now()
        material.category = data.category
        material.material_type = data.material_type
        material.title = data.title or None
        material.business_date = data.business_date.isoformat() if data.business_date else None
        material.period_start = data.period_start.isoformat() if data.period_start else None
        material.period_end = data.period_end.isoformat() if data.period_end else None
        material.notes = data.notes
        material.sensitivity = data.sensitivity
        material.status = "organized"
        material.confirmed_by = actor.id
        material.confirmed_at = timestamp
        material.updated_at = timestamp
        if before is None:
            material.created_at = timestamp
        session.flush()

        session.execute(
            delete(DocumentMaterialProduct).where(
                DocumentMaterialProduct.document_id == doc.id
            )
        )
        for product_id in product_ids:
            session.add(
                DocumentMaterialProduct(
                    manager_id=doc.manager_id,
                    document_id=doc.id,
                    product_id=product_id,
                    created_at=timestamp,
                )
            )
        session.execute(
            delete(DocumentMaterialInvestor).where(
                DocumentMaterialInvestor.document_id == doc.id
            )
        )
        for investor_id in investor_ids:
            session.add(
                DocumentMaterialInvestor(
                    manager_id=doc.manager_id,
                    document_id=doc.id,
                    investor_id=investor_id,
                    created_at=timestamp,
                )
            )

        job = session.scalar(
            select(ParseJob)
            .where(ParseJob.document_id == doc.id)
            .with_for_update()
        )
        if data.category == "nav_valuation":
            parsed_records = (job.result or {}).get("record_ids", []) if job else []
            if not job:
                job = ParseJob(manager_id=doc.manager_id, document_id=doc.id)
                session.add(job)
            elif not parsed_records and job.status not in {"queued", "processing"}:
                job.status = "queued"
                job.result = {
                    key: value
                    for key, value in (job.result or {}).items()
                    if key != "skip_reason"
                }
                job.updated_at = timestamp
        elif (
            job
            and not (job.result or {}).get("record_ids")
            and job.status not in {"processing", "skipped"}
        ):
            job.status = "skipped"
            job.result = {
                **(job.result or {}),
                "skip_reason": "资料已人工确认为非净值类别，不进入净值解析",
            }
            job.updated_at = timestamp

        after = {
            "category": material.category,
            "material_type": material.material_type,
            "title": material.title,
            "business_date": material.business_date,
            "period_start": material.period_start,
            "period_end": material.period_end,
            "product_ids": product_ids,
            "investor_ids": investor_ids,
            "sensitivity": material.sensitivity,
            "notes": material.notes,
            "revision": material.revision,
        }
        audit(
            session,
            actor,
            doc.manager_id,
            "document.material_organized",
            doc.id,
            {"before": before, "after": after},
        )
        session.flush()
        linked_products.sort(key=lambda product: product.name)
        linked_investors.sort(key=lambda investor: investor.display_name)
        return document_result(
            doc, job, material, linked_products, linked_investors
        )

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
        material = session.get(DocumentMaterial, doc.id)
        if material and material.category != "nav_valuation":
            raise HTTPException(422, "该资料已确认为非净值类别，不进入净值解析")
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
        timestamp = now()

        def matches_confirmed_product(candidate):
            candidate_code = str(candidate.get("product_code") or "").strip()
            candidate_name = str(candidate.get("product_name") or "").strip()
            return candidate_code == data.code or (
                not candidate_code and candidate_name == data.name
            )

        # One confirmation is enough for every historical attachment that yielded
        # the same exact product candidate. The raw parse result remains available
        # until the worker replaces it with the successful reparse result.
        requeued_document_ids = []
        pending_jobs = list(
            session.scalars(
                select(ParseJob)
                .where(
                    ParseJob.manager_id == doc.manager_id,
                    ParseJob.status == "review",
                )
                .with_for_update()
            )
        )
        for pending_job in pending_jobs:
            errors = (pending_job.result or {}).get("errors", [])
            if any(
                matches_confirmed_product(error.get("candidate", {}))
                for error in errors
                if error.get("candidate")
            ):
                pending_job.status = "queued"
                pending_job.updated_at = timestamp
                requeued_document_ids.append(pending_job.document_id)
        audit(
            session,
            actor,
            doc.manager_id,
            "product.confirmed_from_document",
            product.id,
            {
                "document_id": doc.id,
                "historical_documents_requeued": len(requeued_document_ids),
                **data.model_dump(),
            },
        )
        return {
            "id": product.id,
            "parse_status": "queued",
            "requeued_documents": len(requeued_document_ids),
        }

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

    @app.post("/api/tasks/{issue_id}/custodian-resend")
    def custodian_resend(issue_id: str, data: S.ReceiptFollowup,
                         actor=Depends(user), session=Depends(db, scope="function")):
        initial = get_issue(session, actor, issue_id)
        issue = lock_missing(session, issue_id, initial.manager_id, data.revision)
        mark_resend(session, issue, actor, data.reason)
        return issue_row(session, issue)

    @app.post("/api/tasks/{issue_id}/material-received")
    def material_received(issue_id: str, data: S.MaterialReceived,
                          actor=Depends(user), session=Depends(db, scope="function")):
        initial = get_issue(session, actor, issue_id)
        document = get_document(session, actor, data.document_id)
        issue = lock_missing(session, issue_id, initial.manager_id, data.revision)
        match_material(session, issue, document, actor, data.reason)
        return issue_row(session, issue)

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

    @app.get("/api/managers/{manager_id}/mail-items")
    def mail_items(
        manager_id: str,
        mailbox_id: str | None = None,
        paginated: bool = False,
        offset: int = Query(0, ge=0),
        limit: int = Query(50, ge=1, le=500),
        q: str = Query("", max_length=500),
        view: str = Query("all", pattern="^(all|action|completed|receipt|pending)$"),
        actor=Depends(user), session=Depends(db, scope="function"),
    ):
        permissions = require(session, actor, manager_id, "archive")
        query = select(MailItem).where(MailItem.manager_id == manager_id)
        if not permissions["investor_read"]:
            query = query.where(MailItem.category != "investor_redemption")
        if mailbox_id:
            box = session.get(Mailbox, mailbox_id)
            if not box or box.manager_id != manager_id:
                raise HTTPException(404, "邮箱不存在")
            query = query.where(MailItem.document_id.in_(
                select(MailReceipt.document_id).where(MailReceipt.mailbox_id == mailbox_id)
            ))
        if view in {"action", "completed"}:
            query = query.where(MailItem.id.in_(select(MailAction.mail_item_id).where(
                MailAction.status == ("open" if view == "action" else "completed")
            )))
        elif view == "receipt":
            query = query.where(MailItem.handling_mode.in_(["receipt", "archive"]))
        elif view == "pending":
            query = query.where(MailItem.handling_mode == "pending")
        if q.strip():
            needle = q.strip()
            query = query.where(or_(
                MailItem.title.contains(needle, autoescape=True),
                MailItem.sender.contains(needle, autoescape=True),
                MailItem.id.in_(select(MailItemProduct.mail_item_id).join(
                    Product, Product.id == MailItemProduct.product_id
                ).where(Product.name.contains(needle, autoescape=True))),
            ))
        total = session.scalar(select(func.count()).select_from(query.subquery())) if paginated else 0
        items = list(session.scalars(query.order_by(
            MailItem.created_at.desc(), MailItem.id.desc()
        ).offset(offset if paginated else 0).limit(limit if paginated else 500)))
        page = {"total": total, "offset": offset, "limit": limit}
        if not items:
            return {**page, "items": []} if paginated else []
        item_ids = [item.id for item in items]
        document_ids = [item.document_id for item in items]
        actions = {
            action.mail_item_id: action
            for action in session.scalars(
                select(MailAction).where(MailAction.mail_item_id.in_(item_ids))
            )
        }
        product_map = {item_id: [] for item_id in item_ids}
        for item_id, product_id, name in session.execute(
            select(MailItemProduct.mail_item_id, Product.id, Product.name)
            .join(Product, MailItemProduct.product_id == Product.id)
            .where(MailItemProduct.mail_item_id.in_(item_ids))
            .order_by(Product.name)
        ):
            product_map[item_id].append({"id": product_id, "name": name})
        source_map = {document_id: [] for document_id in document_ids}
        for document_id, source_mailbox_id, label, username, folder in session.execute(
            select(
                MailReceipt.document_id,
                Mailbox.id,
                Mailbox.label,
                Mailbox.username,
                MailReceipt.folder,
            )
            .join(Mailbox, MailReceipt.mailbox_id == Mailbox.id)
            .where(MailReceipt.document_id.in_(document_ids))
            .order_by(Mailbox.label, MailReceipt.folder)
        ):
            source_map[document_id].append(
                {"mailbox_id": source_mailbox_id, "mailbox": label, "username": username, "folder": folder}
            )
        attachment_counts = dict(
            session.execute(
                select(Document.parent_id, func.count(Document.id))
                .where(Document.parent_id.in_(document_ids))
                .group_by(Document.parent_id)
            ).all()
        )
        result = []
        for item in items:
            result.append(
                {
                    **row(item),
                    "action": row(actions.get(item.id)),
                    "products": product_map[item.id],
                    "sources": source_map[item.document_id],
                    "attachment_count": attachment_counts.get(item.document_id, 0),
                }
            )
        return {**page, "items": result} if paginated else result

    @app.get("/api/mail-items/{item_id}")
    def mail_item_detail(
        item_id: str, actor=Depends(user), session=Depends(db, scope="function")
    ):
        item = session.get(MailItem, item_id)
        if not item:
            raise HTTPException(404, "邮件记录不存在")
        require(session, actor, item.manager_id, "archive")
        if item.category == "investor_redemption":
            require(session, actor, item.manager_id, "investor_read")
        original = get_document(session, actor, item.document_id)
        path = settings.storage / original.storage_key
        if not path.is_file():
            raise HTTPException(503, "邮件原件暂不可用，请联系管理员")
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != original.sha256:
            raise HTTPException(503, "邮件原件完整性校验失败，已阻止展示")
        try:
            message = BytesParser(policy=policy.default).parsebytes(raw)
        except Exception as exc:
            raise HTTPException(422, "邮件原件格式无法展开，请下载原件核对") from exc
        attachments = list(
            session.scalars(
                select(Document)
                .where(Document.parent_id == original.id)
                .order_by(Document.received_at, Document.filename)
            )
        )
        if not rights(session, actor, item.manager_id)["investor_read"]:
            sensitive_document_ids = set(
                session.scalars(
                    select(DocumentMaterial.document_id).where(
                        DocumentMaterial.document_id.in_(
                            [attachment.id for attachment in attachments]
                        ),
                        DocumentMaterial.sensitivity == "investor_sensitive",
                    )
                )
            )
            attachments = [
                attachment
                for attachment in attachments
                if attachment.id not in sensitive_document_ids
            ]
        sources = []
        for label, username, folder in session.execute(
            select(Mailbox.label, Mailbox.username, MailReceipt.folder)
            .join(MailReceipt, MailReceipt.mailbox_id == Mailbox.id)
            .where(MailReceipt.document_id == original.id)
            .order_by(Mailbox.label, MailReceipt.folder)
        ):
            sources.append({"mailbox": label, "username": username, "folder": folder})
        return {
            "id": item.id,
            "document_id": original.id,
            "subject": str(message.get("Subject", "")).strip() or "（无主题邮件）",
            "sender": str(message.get("From", "")).strip(),
            "to": str(message.get("To", "")).strip(),
            "cc": str(message.get("Cc", "")).strip(),
            "sent_at": str(message.get("Date", "")).strip(),
            "received_at": original.received_at,
            "body": full_message_text(message),
            "body_html": safe_message_html(message),
            "category": item.category,
            "business_date": item.business_date,
            "sources": sources,
            "attachments": [
                {
                    "id": attachment.id,
                    "filename": attachment.filename,
                    "size": attachment.size,
                    "media_type": attachment.media_type,
                    "sha256": attachment.sha256,
                }
                for attachment in attachments
            ],
        }

    @app.get("/api/managers/{manager_id}/calendar")
    def operations_calendar(
        manager_id: str,
        month: str,
        actor=Depends(user),
        session=Depends(db, scope="function"),
    ):
        if not re.fullmatch(r"20\d{2}-(?:0[1-9]|1[0-2])", month):
            raise HTTPException(422, "月份格式应为 YYYY-MM")
        manager_permission(session, actor, manager_id)
        year, month_number = (int(value) for value in month.split("-"))
        dates = month_days(year, month_number)
        return {
            "month": month,
            "calendar_version": VERSION,
            "sources": {
                "trading_days": SOURCES.get(year),
                "public_holidays": PUBLIC_HOLIDAY_SOURCES.get(year),
            },
            "refresh": calendar_refresh_status(settings),
            "days": [
                {
                    "date": day.isoformat(),
                    "weekday": day.weekday(),
                    "trading_day": is_trading_day(day),
                    "holiday_name": public_holiday(day),
                    "makeup_workday": is_makeup_workday(day),
                }
                for day in dates
            ],
        }

    @app.post("/api/mail-actions/{action_id}/complete")
    def complete_mail_action(
        action_id: str,
        data: S.MailActionCompletion,
        actor=Depends(user),
        session=Depends(db, scope="function"),
    ):
        action = session.scalar(
            select(MailAction)
            .where(MailAction.id == action_id)
            .with_for_update()
        )
        if not action:
            raise HTTPException(404, "邮件待办不存在")
        require(session, actor, action.manager_id, "write")
        if action.revision != data.revision:
            raise HTTPException(409, "待办已被其他人更新，请刷新后重试")
        if action.status != "open":
            raise HTTPException(409, "待办已经结束")
        action.status = "completed"
        action.result = {"reason": data.reason, "actor_id": actor.id, "at": now()}
        action.updated_at = now()
        action.revision += 1
        item = session.get(MailItem, action.mail_item_id)
        item.status = "completed"
        item.updated_at = now()
        item.revision += 1
        audit(
            session,
            actor,
            action.manager_id,
            "mail_action.completed",
            action.id,
            {"mail_item_id": item.id, "reason": data.reason},
        )
        return {"ok": True, "revision": action.revision}

    @app.put("/api/mail-items/{item_id}/classification")
    def update_mail_classification(
        item_id: str,
        data: S.MailClassification,
        actor=Depends(user),
        session=Depends(db, scope="function"),
    ):
        item = session.scalar(
            select(MailItem).where(MailItem.id == item_id).with_for_update()
        )
        if not item:
            raise HTTPException(404, "邮件记录不存在")
        require(session, actor, item.manager_id, "write")
        if item.revision != data.revision:
            raise HTTPException(409, "邮件分类已被其他人更新，请刷新后重试")
        before = {
            "category": item.category,
            "handling_mode": item.handling_mode,
            "status": item.status,
        }
        apply_manual_classification(
            session,
            item,
            data.category,
            data.handling_mode,
            data.suggested_action,
        )
        audit(
            session,
            actor,
            item.manager_id,
            "mail_item.classified",
            item.id,
            {
                "before": before,
                "after": {
                    "category": item.category,
                    "handling_mode": item.handling_mode,
                    "status": item.status,
                },
            },
        )
        return {"ok": True, "revision": item.revision}

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
