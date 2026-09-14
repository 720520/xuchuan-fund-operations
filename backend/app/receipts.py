"""Receipt scheduling and evidence, separate from NAV validity and email delivery."""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import select

from .db import now
from .models import (ExceptionTask, NavRecord, Product, ReceiptExpectation,
                     ReceiptPolicy, ShareClass)
from .security import audit
from .trading_calendar import (VERSION, CalendarUnavailable, expected_on, is_trading_day,
                               next_trading_day, previous_trading_day)

ZONE = ZoneInfo("Asia/Shanghai")


def local_now():
    return datetime.now(ZONE)


def as_local(value):
    parsed = datetime.fromisoformat(value)
    return parsed.replace(tzinfo=ZONE) if parsed.tzinfo is None else parsed.astimezone(ZONE)


def deadline(item):
    return as_local(f"{item.due_date}T{item.cutoff}:00+08:00")


def missing_issue(db, item):
    return db.scalar(select(ExceptionTask).where(
        ExceptionTask.manager_id == item.manager_id,
        ExceptionTask.dedup_key == f"missing:{item.share_id}:{item.valuation_date}",
    ).with_for_update())


def close_issue(db, item, actor=None, via="material_received"):
    issue = missing_issue(db, item)
    if issue and issue.status != "resolved":
        issue.status = "resolved"
        issue.resolution = {"via": via, "received_at": item.received_at,
                            "record_id": item.record_id, "document_id": item.document_id}
        issue.updated_at = now()
        issue.revision += 1
        audit(db, actor, item.manager_id, "exception.receipt_resolved", issue.id, issue.resolution)


def record_received(db, item, received_at, document_id=None, record_id=None, actor=None):
    if item.received_at is None or as_local(received_at) < as_local(item.received_at):
        item.received_at, item.document_id, item.record_id = received_at, document_id, record_id
        audit(db, actor, item.manager_id, "receipt.material_received", item.id,
              {"share_id": item.share_id, "valuation_date": item.valuation_date,
               "document_id": document_id, "record_id": record_id,
               "received_at": received_at, "late": as_local(received_at) > deadline(item)})
    close_issue(db, item, actor)


def nav_received(db, nav, actor=None):
    # Caller holds the share lock; scheduler and manual evidence use the same lock order.
    item = db.scalar(select(ReceiptExpectation).where(
        ReceiptExpectation.share_id == nav.share_id,
        ReceiptExpectation.valuation_date == nav.valuation_date,
    ).with_for_update())
    if item:
        record_received(db, item, nav.received_at, nav.document_id, nav.id, actor)
        reconcile(db, item, local_now())


def ensure_expectation(db, product, share, valuation_day, followup_time="09:00"):
    db.scalar(select(ShareClass).where(ShareClass.id == share.id).with_for_update())
    item = db.scalar(select(ReceiptExpectation).where(
        ReceiptExpectation.share_id == share.id,
        ReceiptExpectation.valuation_date == valuation_day.isoformat(),
    ))
    if item:
        return item
    due = next_trading_day(valuation_day)
    try:
        followup = next_trading_day(due).isoformat()
    except CalendarUnavailable:
        followup = None  # Due-date checking remains possible at the end of calendar coverage.
    item = ReceiptExpectation(
        manager_id=product.manager_id, product_id=product.id, share_id=share.id,
        valuation_date=valuation_day.isoformat(), due_date=due.isoformat(),
        cutoff="15:00" if product.frequency == "daily" else product.cutoff,
        followup_date=followup, followup_time=followup_time, calendar_version=VERSION,
    )
    db.add(item)
    db.flush()
    return item


def reconcile(db, item, at):
    db.scalar(select(ShareClass).where(ShareClass.id == item.share_id).with_for_update())
    db.refresh(item)
    product = db.get(Product, item.product_id)
    if item.cancelled:
        return
    if product.lifecycle_status in {"liquidated", "archived"} or not product.expected or product.frequency == "off":
        item.cancelled = True
        close_issue(db, item, via="receipt_disabled")
        audit(db, None, item.manager_id, "receipt.cancelled", item.id, {"reason": "product_not_expected"})
        return
    candidates = list(db.scalars(select(NavRecord).where(
        NavRecord.share_id == item.share_id,
        NavRecord.valuation_date == item.valuation_date,
    )))
    if candidates:
        first = min(candidates, key=lambda r: as_local(r.received_at))
        record_received(db, item, first.received_at, first.document_id, first.id)
    if item.received_at and as_local(item.received_at) <= deadline(item):
        return
    if at <= deadline(item):
        return
    # A late arrival can be parsed before this poll: still retain its lateness.
    issue = missing_issue(db, item)
    if issue is None:
        from .services import task
        issue = task(db, item.manager_id, "missing",
                     f"missing:{item.share_id}:{item.valuation_date}",
                     {"expectation_id": item.id, "due_date": item.due_date,
                      "cutoff": item.cutoff, "calendar": item.calendar_version,
                      "followup_date": item.followup_date, "followup_time": item.followup_time,
                      "stage": "late"}, item.product_id, item.share_id, item.valuation_date)
        audit(db, None, item.manager_id, "receipt.late", issue.id, dict(issue.payload))
    if item.received_at:
        close_issue(db, item)
        return
    if not item.followup_date:
        try:
            item.followup_date = next_trading_day(date.fromisoformat(item.due_date)).isoformat()
        except CalendarUnavailable:
            return
    followup_at = as_local(f"{item.followup_date}T{item.followup_time}:00+08:00")
    if at >= followup_at and issue.status != "resolved" and issue.payload.get("stage") != "followup":
        issue.payload = {**issue.payload, "stage": "followup", "followup_date": item.followup_date}
        issue.revision += 1
        issue.updated_at = now()
        audit(db, None, item.manager_id, "receipt.followup_due", issue.id, dict(issue.payload))


def check_receipts(db, manager_id, on_date=None, at=None, policy=None):
    at = (at or local_now()).astimezone(ZONE)
    today = at.date()
    products = list(db.scalars(select(Product).where(
        Product.manager_id == manager_id, Product.expected.is_(True),
        Product.frequency != "off", Product.lifecycle_status.notin_(["liquidated", "archived"]),
    )))
    configured_policy = policy or db.get(ReceiptPolicy, manager_id)
    followup_time = configured_policy.followup_time if configured_policy else "09:00"
    if on_date is not None:
        if not is_trading_day(on_date):
            raise CalendarUnavailable("所选估值日不是交易日，请核对材料日期")
        days = [(on_date, next_trading_day(on_date))]
    else:
        start = date.fromisoformat(policy.last_scheduled_date or policy.start_date) if policy else today
        days = []
        cursor = start
        while cursor <= today:
            if is_trading_day(cursor):
                days.append((previous_trading_day(cursor), cursor))
            cursor += timedelta(days=1)
    for valuation_day, due_day in days:
        for product in products:
            if not expected_on(product, valuation_day):
                continue
            # Do not invent missed receipts before the product existed during automatic catch-up.
            if policy and as_local(product.created_at).date() > due_day:
                continue
            for share in db.scalars(select(ShareClass).where(ShareClass.product_id == product.id)):
                ensure_expectation(db, product, share, valuation_day, followup_time)
    if policy and today >= date.fromisoformat(policy.start_date):
        policy.last_scheduled_date = today.isoformat()
    # Includes unresolved older dates, even after holidays or worker downtime.
    items = list(db.scalars(select(ReceiptExpectation).where(
        ReceiptExpectation.manager_id == manager_id, ReceiptExpectation.cancelled.is_(False),
        ReceiptExpectation.received_at.is_(None),
    )))
    # Also reconcile newly generated already-received dates, to capture late arrivals.
    for item in items:
        reconcile(db, item, at)
    return len(items)


def run_receipt_checks(factory, at=None):
    at = (at or local_now()).astimezone(ZONE)
    with factory() as db:
        managers = list(db.scalars(select(ReceiptPolicy.manager_id).where(ReceiptPolicy.enabled.is_(True))))
    for manager_id in managers:
        try:
            with factory.begin() as db:
                policy = db.scalar(select(ReceiptPolicy).where(
                    ReceiptPolicy.manager_id == manager_id, ReceiptPolicy.enabled.is_(True),
                ).with_for_update(skip_locked=True))
                if not policy or (policy.last_checked_at and (at - as_local(policy.last_checked_at)).total_seconds() < 60):
                    continue
                check_receipts(db, manager_id, at=at, policy=policy)
                policy.last_checked_at, policy.error = at.isoformat(), None
        except Exception as exc:
            # Each manager's transaction is isolated; retry next minute, expose a bounded error.
            with factory.begin() as db:
                policy = db.get(ReceiptPolicy, manager_id)
                policy.error = str(exc)[:250] if isinstance(exc, CalendarUnavailable) else "自动应收检查失败，请联系管理员；下轮会重试"
                policy.last_checked_at = at.isoformat()


def lock_missing(db, issue_id, manager_id, revision):
    initial = db.get(ExceptionTask, issue_id)
    if not initial or initial.manager_id != manager_id or initial.kind != "missing":
        raise HTTPException(422, "只能对当前牌照缺件事项操作")
    db.scalar(select(ShareClass).where(ShareClass.id == initial.share_id).with_for_update())
    issue = db.scalar(select(ExceptionTask).where(ExceptionTask.id == issue_id).with_for_update().execution_options(populate_existing=True))
    if issue.status == "resolved" or issue.revision != revision:
        raise HTTPException(409, "事项已经变化，请刷新后重试")
    return issue


def mark_resend(db, issue, actor, reason):
    payload = {"actor_id": actor.id, "at": now(), "reason": reason}
    issue.payload = {**issue.payload, "last_resend": payload}
    issue.revision += 1
    issue.updated_at = now()
    audit(db, actor, issue.manager_id, "receipt.custodian_resend", issue.id, payload)
    # Remains open until matched material or NAV arrives.


def match_material(db, issue, document, actor, reason):
    if document.manager_id != issue.manager_id:
        raise HTTPException(422, "材料与缺件事项不属于同一牌照")
    if document.product_id and document.product_id != issue.product_id:
        raise HTTPException(422, "材料已关联其他产品")
    if document.media_type == "message/rfc822":
        raise HTTPException(422, "请选择已核对的净值附件，不可仅凭邮件到达确认")
    product = db.get(Product, issue.product_id)
    share = db.get(ShareClass, issue.share_id)
    item = ensure_expectation(db, product, share, date.fromisoformat(issue.valuation_date))
    record_received(db, item, document.received_at, document.id, actor=actor)
    audit(db, actor, issue.manager_id, "receipt.material_matched", item.id,
          {"document_id": document.id, "valuation_date": issue.valuation_date,
           "share_id": issue.share_id, "reason": reason})
