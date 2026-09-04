import hashlib
import os
import re
from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import select, update

from .db import now
from .models import (
    Document,
    EffectiveNav,
    ExceptionTask,
    NavRecord,
    ParseJob,
    Product,
    ShareClass,
    ValidationRule,
)
from .parsing import business_date, numeric, parse
from .security import audit


def task(
    db,
    manager_id,
    kind,
    dedup_key,
    payload,
    product_id=None,
    share_id=None,
    valuation_date=None,
):
    current = db.scalar(
        select(ExceptionTask)
        .where(
            ExceptionTask.manager_id == manager_id, ExceptionTask.dedup_key == dedup_key
        )
        .with_for_update()
    )
    if current:
        if current.status == "resolved":
            # New evidence reopens the same issue, preserving prior resolution in audit.
            audit(
                db,
                None,
                manager_id,
                "exception.reopened",
                current.id,
                {"previous_resolution": current.resolution},
            )
            current.status, current.assignee_id, current.resolution = "open", None, None
        current.payload = {**current.payload, **payload}
        current.updated_at, current.revision = now(), current.revision + 1
        return current
    current = ExceptionTask(
        manager_id=manager_id,
        kind=kind,
        dedup_key=dedup_key,
        payload=payload,
        product_id=product_id,
        share_id=share_id,
        valuation_date=valuation_date,
    )
    db.add(current)
    db.flush()
    return current


def archive(
    db,
    settings,
    manager_id,
    name,
    content,
    source,
    actor=None,
    product_id=None,
    parent_id=None,
    received_at=None,
    metadata=None,
):
    if len(content) > settings.max_upload:
        limit = settings.max_upload // (1024 * 1024)
        raise HTTPException(413, f"文件超出 {limit} MiB 限制")
    if not content:
        raise HTTPException(422, "文件为空")
    name = name.replace("\\", "/").rsplit("/", 1)[-1][:255] or "attachment.bin"
    sha = hashlib.sha256(content).hexdigest()
    key = f"{manager_id}/{sha[:2]}/{sha}"
    path = settings.storage / key
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        path.chmod(0o440)
    except FileExistsError:
        if hashlib.sha256(path.read_bytes()).hexdigest() != sha:
            raise HTTPException(500, "归档完整性异常")
    doc = Document(
        manager_id=manager_id,
        product_id=product_id,
        filename=name,
        sha256=sha,
        storage_key=key,
        size=len(content),
        media_type="message/rfc822"
        if name.lower().endswith(".eml")
        else "application/octet-stream",
        source=source,
        uploader_id=actor.id if actor else None,
        parent_id=parent_id,
        received_at=received_at or now(),
        metadata_json=metadata or {},
    )
    db.add(doc)
    db.flush()
    audit(
        db,
        actor,
        manager_id,
        "document.archived",
        doc.id,
        {"filename": name, "sha256": sha, "source": source},
    )
    return doc


def change_product_lifecycle(
    db,
    settings,
    product,
    actor,
    status,
    effective_date,
    reason,
    material_name=None,
    material_content=None,
):
    allowed = {"active", "liquidating", "liquidated", "archived"}
    if status not in allowed:
        raise HTTPException(422, "产品生命周期状态无效")
    reason = reason.strip()
    if not reason or len(reason) > 2000:
        raise HTTPException(422, "状态变更原因必填且不能超过 2000 字")
    if status == product.lifecycle_status:
        raise HTTPException(422, "产品已经处于该状态")
    if status == "liquidated" and not effective_date:
        raise HTTPException(422, "标记已清算必须填写清算完成日期")
    if status == "liquidated" and material_content is None:
        raise HTTPException(422, "标记已清算必须上传清算报告或托管确认材料")
    if isinstance(effective_date, str):
        effective_date = date.fromisoformat(effective_date)
    today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
    if effective_date and effective_date > today:
        raise HTTPException(422, "状态生效日期不能晚于今天")
    material_doc = None
    if material_content is not None:
        material_doc = archive(
            db,
            settings,
            product.manager_id,
            material_name or "清算材料.bin",
            material_content,
            "lifecycle_material",
            actor,
            product.id,
            metadata={"lifecycle_status": status, "reason": reason},
        )
    before = {
        "status": product.lifecycle_status,
        "date": product.lifecycle_date,
        "reason": product.lifecycle_reason,
        "expected": product.expected,
        "frequency": product.frequency,
    }
    product.lifecycle_status = status
    product.lifecycle_date = (effective_date or today).isoformat()
    product.lifecycle_reason = reason
    product.lifecycle_updated_at = now()
    product.lifecycle_updated_by = actor.id
    if status in {"liquidated", "archived"}:
        product.expected = False
        product.frequency = "off"
        for issue in db.scalars(
            select(ExceptionTask).where(
                ExceptionTask.product_id == product.id,
                ExceptionTask.kind == "missing",
                ExceptionTask.status != "resolved",
            )
        ):
            issue.status = "resolved"
            issue.updated_at = now()
            issue.revision += 1
            issue.resolution = {
                "via": "product_lifecycle_changed",
                "status": status,
                "reason": reason,
            }
    audit(
        db,
        actor,
        product.manager_id,
        "product.lifecycle_changed",
        product.id,
        {
            "before": before,
            "after": {
                "status": status,
                "date": product.lifecycle_date,
                "reason": reason,
                "expected": product.expected,
                "frequency": product.frequency,
            },
            "material_document_id": material_doc.id if material_doc else None,
        },
    )
    return material_doc


def validate_nav(values):
    errors = []
    if Decimal(values["unit_nav"]) <= 0:
        errors.append(
            {
                "rule": "unit_nav_positive",
                "message": "单位净值必须大于零",
                "overridable": False,
            }
        )
    if (
        values["valuation_date"]
        > datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    ):
        errors.append(
            {
                "rule": "future_date",
                "message": "估值日期晚于当前日期",
                "overridable": False,
            }
        )
    for key in ["net_assets", "total_shares"]:
        if values.get(key) is not None and Decimal(values[key]) < 0:
            errors.append(
                {
                    "rule": key + "_nonnegative",
                    "message": "规模或份额不能为负数",
                    "overridable": False,
                }
            )
    return errors


def add_nav(
    db,
    manager_id,
    product,
    share,
    values,
    actor=None,
    document=None,
    row_key=None,
    manual=False,
):
    # Serialize candidates and effective pointer per share. PostgreSQL lock is the production guarantee.
    db.scalar(select(ShareClass).where(ShareClass.id == share.id).with_for_update())
    values = {**values, "valuation_date": business_date(values["valuation_date"])}
    for key in ["unit_nav", "accumulated_nav", "net_assets", "total_shares"]:
        values[key] = numeric(values.get(key), key)
    if not values["unit_nav"]:
        raise HTTPException(422, "缺少单位净值")
    if document and row_key:
        prior = db.scalar(
            select(NavRecord).where(
                NavRecord.document_id == document.id, NavRecord.row_key == row_key
            )
        )
        if prior:
            return prior
    validation = validate_nav(values)
    if values.get("currency") and values["currency"] != product.currency:
        validation.append(
            {
                "rule": "currency_mismatch",
                "message": "币种与产品不符",
                "overridable": False,
            }
        )
    rule = db.get(ValidationRule, manager_id)
    if not validation and rule and rule.max_nav_change is not None:
        previous = db.scalar(
            select(NavRecord)
            .join(EffectiveNav, EffectiveNav.record_id == NavRecord.id)
            .where(
                NavRecord.share_id == share.id,
                NavRecord.valuation_date < values["valuation_date"],
            )
            .order_by(NavRecord.valuation_date.desc())
            .limit(1)
        )
        if previous:
            change = abs(Decimal(values["unit_nav"]) / Decimal(previous.unit_nav) - 1)
            if change > rule.max_nav_change:
                validation.append(
                    {
                        "rule": "nav_change_threshold",
                        "message": "较上一有效估值日的净值变化超出管理员配置阈值",
                        "overridable": True,
                        "change": str(change),
                        "threshold": str(rule.max_nav_change),
                        "base_record_id": previous.id,
                    }
                )
    nav = NavRecord(
        manager_id=manager_id,
        product_id=product.id,
        share_id=share.id,
        valuation_date=values["valuation_date"],
        unit_nav=values["unit_nav"],
        accumulated_nav=values.get("accumulated_nav"),
        net_assets=values.get("net_assets"),
        total_shares=values.get("total_shares"),
        source="manual" if not document or manual else document.source,
        document_id=document.id if document else None,
        actor_id=actor.id if actor else None,
        row_key=row_key,
        received_at=document.received_at if document else now(),
        validation=validation,
        reported_metrics={
            k: values[k]
            for k in ["cash", "position_ratio", "return_rate", "drawdown"]
            if values.get(k) is not None
        },
    )
    db.add(nav)
    db.flush()
    effective = db.get(EffectiveNav, (share.id, nav.valuation_date))
    if validation:
        task(
            db,
            manager_id,
            "validation",
            f"validation:{nav.id}",
            {"record_ids": [nav.id], "errors": validation},
            product.id,
            share.id,
            nav.valuation_date,
        )
    elif effective:
        old = db.get(NavRecord, effective.record_id)
        fields = ["unit_nav", "accumulated_nav", "net_assets", "total_shares"]

        def as_decimal(value):
            return Decimal(value) if value is not None else None

        if (
            any(
                as_decimal(getattr(old, key)) != as_decimal(getattr(nav, key))
                for key in fields
            )
            or old.reported_metrics != nav.reported_metrics
        ):
            candidates = list(
                db.scalars(
                    select(NavRecord.id).where(
                        NavRecord.share_id == share.id,
                        NavRecord.valuation_date == nav.valuation_date,
                    )
                )
            )
            task(
                db,
                manager_id,
                "conflict",
                f"conflict:{share.id}:{nav.valuation_date}",
                {"record_ids": candidates},
                product.id,
                share.id,
                nav.valuation_date,
            )
    else:
        db.add(
            EffectiveNav(
                manager_id=manager_id,
                share_id=share.id,
                valuation_date=nav.valuation_date,
                record_id=nav.id,
            )
        )
    audit(
        db,
        actor,
        manager_id,
        "nav.received",
        nav.id,
        {
            "product_id": product.id,
            "share_id": share.id,
            "valuation_date": nav.valuation_date,
            "validation": validation,
        },
    )
    # Receipt resolves missing only; validation/conflict tasks remain independent.
    missing = db.scalar(
        select(ExceptionTask).where(
            ExceptionTask.manager_id == manager_id,
            ExceptionTask.dedup_key == f"missing:{share.id}:{nav.valuation_date}",
            ExceptionTask.status != "resolved",
        )
    )
    if missing:
        missing.status, missing.resolution, missing.updated_at = (
            "resolved",
            {"via": "data_received", "record_id": nav.id},
            now(),
        )
        missing.revision += 1
        audit(
            db,
            actor,
            manager_id,
            "exception.receipt_resolved",
            missing.id,
            missing.resolution,
        )
    return nav


def process_document(db, settings, document, actor=None):
    job = db.scalar(
        select(ParseJob).where(ParseJob.document_id == document.id).with_for_update()
    )
    if not job:
        job = ParseJob(manager_id=document.manager_id, document_id=document.id)
        db.add(job)
        db.flush()
    job.status, job.updated_at = "processing", now()
    path = settings.storage / document.storage_key
    try:
        metadata = dict(document.metadata_json or {})
        if document.parent_id:
            parent = db.get(Document, document.parent_id)
            if parent:
                metadata = {**(parent.metadata_json or {}), **metadata}
        sender = metadata.get("from", "")
        domain_match = re.search(r"@([A-Za-z0-9.-]+)", sender)
        context = {
            "sender": sender,
            "sender_domain": domain_match.group(1).lower() if domain_match else "",
            "subject": metadata.get("subject", ""),
            "source": document.source,
        }
        result = parse(
            document.filename, path.read_bytes(), settings.max_rows, context=context
        )
    except Exception as exc:
        # Preserve raw evidence and expose only bounded parser diagnostics.
        result = {
            "records": [],
            "errors": [{"reason": str(exc)[:300]}],
            "parser_version": "explicit-header-v2",
        }
    imported = []
    for item in result["records"]:
        query = select(Product).where(Product.manager_id == document.manager_id)
        matched_by_name = False
        if document.product_id:
            query = query.where(Product.id == document.product_id)
        elif item.get("product_code"):
            query = query.where(Product.code == item["product_code"])
        else:
            query = query.where(Product.name == item.get("product_name"))
        matches = list(db.scalars(query))
        if (
            not matches
            and not document.product_id
            and item.get("product_name")
            and result.get("parser_version", "").startswith("custodian:")
        ):
            matches = list(
                db.scalars(
                    select(Product).where(
                        Product.manager_id == document.manager_id,
                        Product.name == item["product_name"],
                    )
                )
            )
            matched_by_name = len(matches) == 1
        if len(matches) != 1:
            result["errors"].append(
                {
                    "row": item["row_key"],
                    "reason": "产品未建档或名称不唯一，需人工确认产品归属",
                    "candidate": item,
                }
            )
            continue
        product = matches[0]
        if (
            item.get("product_code")
            and product.code != item["product_code"]
            and not matched_by_name
        ):
            result["errors"].append(
                {
                    "row": item["row_key"],
                    "reason": "附件产品代码与指定产品不符，禁止强行关联",
                }
            )
            continue
        if not item.get("product_code") and item.get("product_name") != product.name:
            result["errors"].append(
                {
                    "row": item["row_key"],
                    "reason": "附件产品名称与指定产品不符，禁止强行关联",
                }
            )
            continue
        shares = list(
            db.scalars(select(ShareClass).where(ShareClass.product_id == product.id))
        )
        if item.get("share_class"):
            shares = [s for s in shares if s.name == item["share_class"]]
        if len(shares) != 1:
            result["errors"].append(
                {"row": item["row_key"], "reason": "份额无法唯一识别，需先维护产品份额"}
            )
            continue
        # Cumulative-history attachments repeat earlier rows on every delivery.
        # Reuse an identical canonical record instead of creating thousands of
        # duplicate candidates; a changed value still becomes a new conflict.
        def same_number(left, right):
            return (Decimal(left) if left is not None else None) == (
                Decimal(right) if right is not None else None
            )

        identical = next(
            (
                prior
                for prior in db.scalars(
                    select(NavRecord).where(
                        NavRecord.manager_id == document.manager_id,
                        NavRecord.product_id == product.id,
                        NavRecord.share_id == shares[0].id,
                        NavRecord.valuation_date == item["valuation_date"],
                    )
                )
                if all(
                    same_number(getattr(prior, field), item.get(field))
                    for field in [
                        "unit_nav",
                        "accumulated_nav",
                        "net_assets",
                        "total_shares",
                    ]
                )
            ),
            None,
        )
        if identical:
            imported.append(identical.id)
            continue
        nav = add_nav(
            db,
            document.manager_id,
            product,
            shares[0],
            item,
            actor,
            document,
            item["row_key"],
        )
        imported.append(nav.id)
    job.result = {**result, "record_ids": imported}
    job.status, job.updated_at = ("review" if result["errors"] else "completed"), now()
    if result["errors"]:
        task(
            db,
            document.manager_id,
            "parse",
            f"parse:{document.id}",
            {"document_id": document.id, "job_id": job.id, "errors": result["errors"]},
            document.product_id,
        )
    else:
        old = db.scalar(
            select(ExceptionTask).where(
                ExceptionTask.manager_id == document.manager_id,
                ExceptionTask.dedup_key == f"parse:{document.id}",
            )
        )
        if old and old.status != "resolved":
            old.status, old.resolution, old.updated_at = (
                "resolved",
                {"via": "reparse", "record_ids": imported},
                now(),
            )
            old.revision += 1
            audit(
                db,
                actor,
                document.manager_id,
                "exception.parse_resolved",
                old.id,
                old.resolution,
            )
    audit(
        db,
        actor,
        document.manager_id,
        "document.parsed",
        document.id,
        {"status": job.status, "records": len(imported)},
    )
    return job


def select_effective(db, user, issue, record_id, reversal, reason, revision):
    if issue.status == "resolved":
        raise HTTPException(409, "该待办已经解决")
    record = db.get(NavRecord, record_id)
    if (
        not record
        or record.manager_id != issue.manager_id
        or record.share_id != issue.share_id
        or record.valuation_date != issue.valuation_date
        or record_id not in issue.payload.get("record_ids", [])
    ):
        raise HTTPException(422, "该记录不属于此异常")
    if any(not v.get("overridable") for v in record.validation):
        raise HTTPException(422, "记录有不可豁免的校验错误，需提交正确数据")
    if (reversal or issue.kind == "validation") and not reason.strip():
        raise HTTPException(422, "反账或异常接受必须填写原因")
    db.scalar(
        select(ShareClass).where(ShareClass.id == record.share_id).with_for_update()
    )
    changed = db.execute(
        update(ExceptionTask)
        .where(
            ExceptionTask.id == issue.id,
            ExceptionTask.revision == revision,
            ExceptionTask.status != "resolved",
        )
        .values(
            status="resolved",
            updated_at=now(),
            revision=revision + 1,
            resolution={"record_id": record.id, "reversal": reversal, "reason": reason},
        )
    ).rowcount
    if not changed:
        raise HTTPException(409, "待办已更新，请刷新后处理")
    effective = db.get(EffectiveNav, (record.share_id, record.valuation_date))
    old_id = effective.record_id if effective else None
    if not effective:
        effective = EffectiveNav(
            manager_id=record.manager_id,
            share_id=record.share_id,
            valuation_date=record.valuation_date,
            record_id=record.id,
        )
        db.add(effective)
    else:
        effective.record_id, effective.revision = record.id, effective.revision + 1
    effective.reversal = reversal
    audit(
        db,
        user,
        record.manager_id,
        "nav.reversal" if reversal else "nav.selected",
        record.id,
        {
            "before_record_id": old_id,
            "after_record_id": record.id,
            "reason": reason,
            "valuation_date": record.valuation_date,
            "exception_id": issue.id,
        },
    )


def performance(records):
    # Published accumulated NAV is not assumed to be a reinvested total-return index.
    peak = None
    result = []
    for record in records:
        value = Decimal(record.unit_nav)
        peak = max(peak, value) if peak is not None else value
        result.append(
            {
                "date": record.valuation_date,
                "nav": str(value),
                "nav_change": str(value / Decimal(records[0].unit_nav) - 1),
                "nav_drawdown": str(value / peak - 1),
            }
        )
    return result


def refresh_missing(db, manager_id, on_date=None, at=None):
    local = at or datetime.now(ZoneInfo("Asia/Shanghai"))
    expected_date = on_date or (local.date() - timedelta(days=1))
    while not on_date and expected_date.weekday() >= 5:
        expected_date -= timedelta(days=1)
    for p in db.scalars(
        select(Product).where(
            Product.manager_id == manager_id,
            Product.expected.is_(True),
            Product.lifecycle_status.notin_(["liquidated", "archived"]),
        )
    ):
        if p.frequency == "off":
            continue
        d = expected_date
        if p.frequency == "weekly" and not on_date:
            d = local.date() - timedelta(days=local.weekday() + 7 - p.weekday)
        if local.strftime("%H:%M") < p.cutoff:
            continue
        for share in db.scalars(
            select(ShareClass).where(ShareClass.product_id == p.id)
        ):
            if not db.scalar(
                select(NavRecord.id)
                .where(
                    NavRecord.share_id == share.id,
                    NavRecord.valuation_date == d.isoformat(),
                )
                .limit(1)
            ):
                task(
                    db,
                    manager_id,
                    "missing",
                    f"missing:{share.id}:{d.isoformat()}",
                    {
                        "cutoff": p.cutoff,
                        "check_date": local.date().isoformat(),
                        "calendar": "weekdays-only; holidays require explicit date",
                    },
                    p.id,
                    share.id,
                    d.isoformat(),
                )
