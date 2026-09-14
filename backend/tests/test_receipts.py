from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from app.models import (AuditEvent, Product, ReceiptExpectation,
                        ReceiptPolicy)
from app.receipts import run_receipt_checks
from app.trading_calendar import (CalendarUnavailable, is_trading_day,
                                  next_trading_day, previous_trading_day)
from conftest import login, nav_data, product
from sqlalchemy import select

ZONE = ZoneInfo("Asia/Shanghai")


def at(day, clock="15:01"):
    return datetime.fromisoformat(f"{day}T{clock}:00").replace(tzinfo=ZONE)


def setup_product(env, frequency="daily"):
    app, client, ids = env
    login(client)
    p = product(client, ids["a"])
    with app.state.factory.begin() as db:
        obj = db.get(Product, p["id"])
        obj.created_at = "2026-08-01T00:00:00+08:00"
        obj.frequency = frequency
    return app, client, ids, p


def enable(app, manager, start="2026-09-04"):
    with app.state.factory.begin() as db:
        db.add(ReceiptPolicy(manager_id=manager, enabled=True, start_date=start, followup_time="09:00"))


def issues(client, manager):
    return client.get(f"/api/managers/{manager}/tasks").json()


def test_calendar_holidays_weekends_year_boundary_and_no_guess():
    assert previous_trading_day(date(2026, 9, 28)) == date(2026, 9, 24)
    assert previous_trading_day(date(2026, 10, 8)) == date(2026, 9, 30)
    assert previous_trading_day(date(2026, 1, 5)) == date(2025, 12, 31)
    assert next_trading_day(date(2026, 2, 13)) == date(2026, 2, 24)
    assert not is_trading_day(date(2026, 9, 20))  # compensating workday remains closed
    with pytest.raises(CalendarUnavailable):
        is_trading_day(date(2027, 1, 4))


def test_cutoff_followup_and_stable_revision(env):
    app, client, ids, p = setup_product(env)
    enable(app, ids["a"])
    run_receipt_checks(app.state.factory, at("2026-09-04", "15:00"))
    assert issues(client, ids["a"]) == []
    run_receipt_checks(app.state.factory, at("2026-09-04", "15:01"))
    first = issues(client, ids["a"])[0]
    assert first["valuation_date"] == "2026-09-03"
    assert first["payload"]["stage"] == "late"
    assert first["payload"]["followup_date"] == "2026-09-07"
    run_receipt_checks(app.state.factory, at("2026-09-05", "10:00"))
    run_receipt_checks(app.state.factory, at("2026-09-07", "08:59"))
    assert issues(client, ids["a"])[0]["revision"] == first["revision"]
    run_receipt_checks(app.state.factory, at("2026-09-07", "09:00"))
    current = issues(client, ids["a"])[0]
    assert current["payload"]["stage"] == "followup"
    assert current["revision"] == first["revision"] + 1
    run_receipt_checks(app.state.factory, at("2026-09-07", "09:01"))
    assert issues(client, ids["a"])[0]["revision"] == current["revision"]


def test_worker_catches_up_missed_trading_days_without_duplicates(env):
    app, client, ids, p = setup_product(env)
    enable(app, ids["a"])
    run_receipt_checks(app.state.factory, at("2026-09-04"))
    run_receipt_checks(app.state.factory, at("2026-09-09"))
    result = issues(client, ids["a"])
    assert {i["valuation_date"] for i in result} == {"2026-09-03", "2026-09-04", "2026-09-07", "2026-09-08"}
    run_receipt_checks(app.state.factory, at("2026-09-09", "15:02"))
    assert len(issues(client, ids["a"])) == 4


def test_disabled_policy_and_future_start_do_not_generate_work(env):
    app, client, ids, p = setup_product(env)
    run_receipt_checks(app.state.factory, at("2026-09-04"))
    assert issues(client, ids["a"]) == []
    enable(app, ids["a"], "2026-09-08")
    run_receipt_checks(app.state.factory, at("2026-09-07"))
    assert issues(client, ids["a"]) == []


def test_weekly_holiday_rolls_back_and_summary_matches(env):
    app, client, ids, p = setup_product(env, "weekly")
    enable(app, ids["a"], "2026-09-24")
    run_receipt_checks(app.state.factory, at("2026-09-24"))
    run_receipt_checks(app.state.factory, at("2026-09-25"))
    assert issues(client, ids["a"]) == []
    run_receipt_checks(app.state.factory, at("2026-09-28", "16:00"))
    result = issues(client, ids["a"])
    assert len(result) == 1 and result[0]["valuation_date"] == "2026-09-24"
    assert client.get(f"/api/managers/{ids['a']}/summary?valuation_date=2026-09-23").json()["expected"] == 0
    assert client.get(f"/api/managers/{ids['a']}/summary?valuation_date=2026-09-24").json()["expected"] == 1


def test_resend_is_audited_keeps_missing_and_checks_revision_and_tenant(env):
    app, client, ids, p = setup_product(env)
    enable(app, ids["a"])
    run_receipt_checks(app.state.factory, at("2026-09-04"))
    item = issues(client, ids["a"])[0]
    url = f"/api/tasks/{item['id']}/custodian-resend"
    body = {"revision": item["revision"], "reason": "已在托管平台请求补发"}
    result = client.post(url, json=body)
    assert result.status_code == 200
    assert result.json()["status"] == "open"
    assert result.json()["payload"]["last_resend"]["actor_id"] == ids["ops"]
    assert client.post(url, json=body).status_code == 409
    with app.state.factory() as db:
        assert db.scalar(select(AuditEvent).where(AuditEvent.action == "receipt.custodian_resend"))
    login(client, "otherops")
    assert client.post(url, json=body).status_code == 403


def test_received_unparseable_material_closes_only_missing(env):
    app, client, ids, p = setup_product(env)
    enable(app, ids["a"])
    run_receipt_checks(app.state.factory, at("2026-09-04"))
    missing = issues(client, ids["a"])[0]
    doc = client.post(f"/api/managers/{ids['a']}/documents", files={"file": ("托管净值.pdf", b"unparsed", "application/pdf")}).json()
    # An upload alone does not prove the share/date match.
    assert issues(client, ids["a"])[0]["status"] == "open"
    from app.worker import parse_one
    parse_one(app.state.factory, app.state.settings)
    assert any(i["kind"] == "parse" for i in issues(client, ids["a"]))
    response = client.post(f"/api/tasks/{missing['id']}/material-received", json={
        "document_id": doc["id"], "revision": missing["revision"], "reason": "原件已核对为该份额估值日净值，等待解析适配",
    })
    assert response.status_code == 200, response.text
    result = issues(client, ids["a"])
    assert next(i for i in result if i["kind"] == "missing")["status"] == "resolved"
    assert next(i for i in result if i["kind"] == "parse")["status"] == "open"
    summary = client.get(f"/api/managers/{ids['a']}/summary?valuation_date=2026-09-03").json()
    assert summary["received"] == 1 and summary["confirmed"] == 0
    run_receipt_checks(app.state.factory, at("2026-09-04", "16:00"))
    assert next(i for i in issues(client, ids["a"]) if i["kind"] == "missing")["status"] == "resolved"


def test_cross_manager_material_cannot_close_missing(env):
    app, client, ids, p = setup_product(env)
    enable(app, ids["a"])
    run_receipt_checks(app.state.factory, at("2026-09-04"))
    missing = issues(client, ids["a"])[0]
    login(client, "otherops")
    doc = client.post(f"/api/managers/{ids['b']}/documents", files={"file": ("other.csv", b"data", "text/csv")}).json()
    login(client)
    response = client.post(f"/api/tasks/{missing['id']}/material-received", json={"document_id": doc["id"], "revision": missing["revision"], "reason": "不应允许"})
    assert response.status_code == 403
    assert issues(client, ids["a"])[0]["status"] == "open"


def test_nav_arrival_keeps_validation_issue_and_no_reopen(env):
    app, client, ids, p = setup_product(env)
    enable(app, ids["a"])
    run_receipt_checks(app.state.factory, at("2026-09-04"))
    assert client.post(f"/api/managers/{ids['a']}/nav", json=nav_data(p, "-1", "2026-09-03")).status_code == 201
    run_receipt_checks(app.state.factory, at("2026-09-07", "09:00"))
    result = issues(client, ids["a"])
    assert next(i for i in result if i["kind"] == "missing")["status"] == "resolved"
    assert next(i for i in result if i["kind"] == "validation")["status"] == "open"


def test_calendar_expiry_visible_and_does_not_guess_future(env):
    app, client, ids, p = setup_product(env)
    enable(app, ids["a"], "2027-01-04")
    run_receipt_checks(app.state.factory, at("2027-01-04"))
    with app.state.factory() as db:
        assert "2027" in db.get(ReceiptPolicy, ids["a"]).error
        assert not db.scalar(select(ReceiptExpectation))


def test_policy_auth_start_and_disable_are_audited(env, monkeypatch):
    import app.main as main
    monkeypatch.setattr(main, "local_now", lambda: at("2026-09-07", "10:00"))
    app, client, ids, p = setup_product(env)
    path = f"/api/managers/{ids['a']}/receipt-policy"
    body = {"enabled": True, "start_date": "2026-09-07", "followup_time": "10:30", "calendar_confirmed": True}
    assert client.put(path, json={**body, "start_date": "2026-09-04"}).status_code == 422
    assert client.put(path, json=body).status_code == 200
    assert client.get(path).json()["followup_time"] == "10:30"
    assert client.put(path, json={**body, "start_date": "2026-09-08"}).status_code == 422
    login(client, "colleague")
    assert client.put(path, json=body).status_code == 403
    login(client)
    assert client.put(path, json={**body, "enabled": False}).status_code == 200
    with app.state.factory() as db:
        assert len(list(db.scalars(select(AuditEvent).where(AuditEvent.action == "receipt.policy_updated")))) == 2


def test_clean_nav_before_cutoff_no_late_issue_and_late_arrival_retained(env):
    app, client, ids, p = setup_product(env)
    enable(app, ids["a"])
    # Explicit source arrival is earlier than platform parsing; never use sync time to call it late.
    from app.services import add_nav
    from app.models import ShareClass
    with app.state.factory.begin() as db:
        obj = db.get(Product, p["id"])
        share = db.get(ShareClass, p["shares"][0]["id"])
        from app.services import archive
        doc = archive(db, app.state.settings, ids["a"], "on-time.csv", b"test", "email", received_at="2026-09-04T06:59:00+00:00")
        add_nav(db, ids["a"], obj, share, nav_data(p, "1.0", "2026-09-03"), document=doc)
    run_receipt_checks(app.state.factory, at("2026-09-04", "16:00"))
    assert issues(client, ids["a"]) == []
    with app.state.factory.begin() as db:
        obj = db.get(Product, p["id"])
        share = db.get(ShareClass, p["shares"][0]["id"])
        doc = archive(db, app.state.settings, ids["a"], "late.csv", b"late", "email", received_at="2026-09-07T07:01:00+00:00")
        add_nav(db, ids["a"], obj, share, nav_data(p, "1.01", "2026-09-04"), document=doc)
    run_receipt_checks(app.state.factory, at("2026-09-07", "16:00"))
    result = issues(client, ids["a"])
    assert len(result) == 1 and result[0]["status"] == "resolved"
    assert result[0]["payload"]["stage"] == "late"


def test_liquidated_and_new_products_are_not_backfilled(env):
    app, client, ids, p = setup_product(env)
    with app.state.factory.begin() as db:
        db.get(Product, p["id"]).created_at = "2026-09-08T00:00:00+08:00"
    enable(app, ids["a"])
    run_receipt_checks(app.state.factory, at("2026-09-07"))
    assert issues(client, ids["a"]) == []
    with app.state.factory.begin() as db:
        db.get(Product, p["id"]).lifecycle_status = "liquidated"
    run_receipt_checks(app.state.factory, at("2026-09-08"))
    assert issues(client, ids["a"]) == []


def test_manual_check_uses_configured_followup_and_off_cancels_old_receipts(env):
    from app.receipts import check_receipts
    app, client, ids, p = setup_product(env)
    enable(app, ids["a"])
    with app.state.factory.begin() as db:
        db.get(ReceiptPolicy, ids["a"]).followup_time = "10:30"
        check_receipts(db, ids["a"], on_date=date(2026, 9, 3), at=at("2026-09-04"))
    item = issues(client, ids["a"])[0]
    assert item["payload"]["followup_time"] == "10:30"
    assert client.put(f"/api/products/{p['id']}/schedule", json={"expected": False, "frequency": "off", "weekday": 4, "cutoff": "15:00"}).status_code == 200
    assert issues(client, ids["a"])[0]["status"] == "resolved"
    assert client.put(f"/api/products/{p['id']}/schedule", json={"expected": True, "frequency": "daily", "weekday": 4, "cutoff": "11:00"}).status_code == 200
    run_receipt_checks(app.state.factory, at("2026-09-04", "16:00"))
    assert issues(client, ids["a"])[0]["status"] == "resolved"
    with app.state.factory() as db:
        assert db.scalar(select(ReceiptExpectation)).cancelled
