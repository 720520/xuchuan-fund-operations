import hashlib
import io
from datetime import datetime
from decimal import Decimal
from email.message import EmailMessage
from zoneinfo import ZoneInfo

import pytest
from app.mail_sync import ingest_message
from app.models import Document, Mailbox, NavRecord, ParseJob, ProductGrant
from app.parsing import parse
from app.services import refresh_missing
from app.worker import run_once
from conftest import PASSWORD, login, nav_data, product
from openpyxl import Workbook
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError


def test_auth_origin_and_revocation(env):
    app, client, ids = env
    assert client.get("/api/auth/me").status_code == 401
    assert (
        client.post(
            "/api/auth/login",
            headers={"origin": "https://evil.invalid"},
            json={"email": "ops@test.invalid", "password": PASSWORD},
        ).status_code
        == 403
    )
    login(client)
    assert (
        "httponly" in client.cookies.get("xuchuan_session", "").lower()
        or "xuchuan_session" in client.cookies
    )
    assert (
        client.post(
            "/api/auth/password",
            json={"old_password": PASSWORD, "new_password": PASSWORD + "new"},
        ).status_code
        == 200
    )
    assert client.get("/api/auth/me").status_code == 401


def test_login_throttle(env):
    _, client, _ = env
    for _ in range(5):
        assert (
            client.post(
                "/api/auth/login",
                json={"email": "ops@test.invalid", "password": "wrong"},
            ).status_code
            == 401
        )
    assert (
        client.post(
            "/api/auth/login", json={"email": "ops@test.invalid", "password": PASSWORD}
        ).status_code
        == 429
    )


def test_group_read_does_not_grant_cross_license_write(env):
    _, client, ids = env
    login(client, "otherops")
    b = product(client, ids["b"])
    login(client)
    assert len(client.get(f"/api/managers/{ids['b']}/products").json()) == 1
    assert (
        client.post(f"/api/managers/{ids['b']}/nav", json=nav_data(b)).status_code
        == 403
    )
    assert client.get(f"/api/managers/{ids['c']}/products").status_code == 403
    assert (
        client.post(f"/api/managers/{ids['a']}/nav", json=nav_data(b)).status_code
        == 403
    )
    login(client, "admin")
    assert (
        client.post(
            f"/api/managers/{ids['a']}/products",
            json={"code": "NO", "name": "NO", "shares": ["A"]},
        ).status_code
        == 201
    )


def test_conflict_reversal_immutable_and_stale_revision(env):
    app, client, ids = env
    login(client)
    p = product(client, ids["a"], shares=["A", "B"])
    first = client.post(f"/api/managers/{ids['a']}/nav", json=nav_data(p)).json()
    second = client.post(
        f"/api/managers/{ids['a']}/nav", json=nav_data(p, "1.0800")
    ).json()
    issue = client.get(f"/api/managers/{ids['a']}/tasks").json()[0]
    assert issue["kind"] == "conflict"
    payload = {
        "record_id": second["id"],
        "reversal": True,
        "reason": "托管份额补录反账",
        "revision": issue["revision"],
    }
    login(client, "fund")
    assert (
        client.post(f"/api/tasks/{issue['id']}/resolve", json=payload).status_code
        == 200
    )
    assert (
        client.post(f"/api/tasks/{issue['id']}/resolve", json=payload).status_code
        == 409
    )
    login(client)
    history = client.get(
        f"/api/products/{p['id']}/nav", params={"share_id": p["shares"][0]["id"]}
    ).json()
    assert len(history["versions"]) == 2
    assert history["effective"][0]["id"] == second["id"]
    assert history["effective"][0]["valuation_date"] == "2026-08-28"
    assert (
        next(v for v in history["versions"] if v["id"] == second["id"])["reversal"]
        is True
    )
    with app.state.factory() as db:
        assert Decimal(db.get(NavRecord, first["id"]).unit_nav) == Decimal("1.05")
    for sql in [
        "UPDATE nav_records SET unit_nav = 9",
        "DELETE FROM nav_records",
        "UPDATE audit_events SET action='oops'",
        "DELETE FROM audit_events",
    ]:
        with pytest.raises(DBAPIError), app.state.engine.begin() as connection:
            connection.execute(text(sql))


def test_identical_value_does_not_create_conflict(env):
    _, client, ids = env
    login(client)
    p = product(client, ids["a"])
    for value in ["1.05", "1.0500000000"]:
        assert (
            client.post(
                f"/api/managers/{ids['a']}/nav", json=nav_data(p, value)
            ).status_code
            == 201
        )
    assert client.get(f"/api/managers/{ids['a']}/tasks").json() == []


def test_upload_parse_durable_idempotent_and_download_scope(env):
    app, client, ids = env
    login(client)
    p = product(client, ids["a"])
    content = "产品代码,份额类别,估值日期,单位净值,资产净值,仓位,现金\nF001,A,2026-08-28,1.1234,10000000,45%,5000000\n".encode()
    doc = client.post(
        f"/api/managers/{ids['a']}/documents",
        files={"file": ("nav.csv", content, "text/csv")},
    ).json()
    assert doc["sha256"] == hashlib.sha256(content).hexdigest()
    run_once(app.state.factory, app.state.settings)
    run_once(app.state.factory, app.state.settings)
    docs = client.get(f"/api/managers/{ids['a']}/documents").json()
    assert docs[0]["job"]["status"] == "completed"
    assert len(docs[0]["job"]["result"]["record_ids"]) == 1
    history = client.get(
        f"/api/products/{p['id']}/nav", params={"share_id": p["shares"][0]["id"]}
    ).json()
    assert history["effective"][0]["reported_metrics"]["position_ratio"] == "0.45"
    response = client.get(f"/api/documents/{doc['id']}/download")
    assert response.content == content
    assert "attachment" in response.headers["content-disposition"]
    assert client.post(f"/api/documents/{doc['id']}/reparse").status_code == 200
    run_once(app.state.factory, app.state.settings)
    with app.state.factory() as db:
        assert len(list(db.scalars(select(NavRecord)))) == 1
    login(client, "colleague")
    assert client.get(f"/api/documents/{doc['id']}/download").status_code == 403
    login(client, "otherops")
    assert client.get(f"/api/managers/{ids['a']}/documents").status_code == 403
    assert client.get(f"/api/documents/{doc['id']}/download").status_code == 403
    with pytest.raises(DBAPIError), app.state.engine.begin() as c:
        c.execute(text("DELETE FROM documents"))


def test_unknown_product_can_be_created_then_reparsed(env):
    app, client, ids = env
    login(client)
    content = "产品代码,产品名称,份额类别,估值日期,单位净值\nF001,未知新产品,A,2026-08-28,1.05\n".encode()
    response = client.post(
        f"/api/managers/{ids['a']}/documents", files={"file": ("new.csv", content)}
    )
    assert response.status_code == 201
    run_once(app.state.factory, app.state.settings)
    issue = client.get(f"/api/managers/{ids['a']}/tasks").json()[0]
    assert issue["payload"]["errors"][0]["candidate"]["product_code"] == "F001"
    assert client.get(f"/api/managers/{ids['a']}/products").json() == []
    confirmed = client.post(
        f"/api/documents/{response.json()['id']}/confirm-product",
        json={"code": "F001", "name": "未知新产品", "shares": ["A"]},
    )
    assert confirmed.status_code == 201, confirmed.text
    run_once(app.state.factory, app.state.settings)
    assert len(client.get(f"/api/managers/{ids['a']}/products").json()) == 1
    assert (
        client.get(f"/api/managers/{ids['a']}/tasks").json()[0]["status"] == "resolved"
    )


def test_product_filing_completes_into_product(env):
    _, client, ids = env
    login(client, "admin")
    created = client.post(
        f"/api/managers/{ids['a']}/product-filings",
        json={"code": "FILE001", "name": "备案产品", "shares": ["A", "B"]},
    )
    assert created.status_code == 201, created.text
    filing = created.json()
    assert filing["status"] == "in_progress"
    assert client.get(f"/api/managers/{ids['a']}/products").json() == []
    completed = client.post(f"/api/product-filings/{filing['id']}/complete")
    assert completed.status_code == 200, completed.text
    products = client.get(f"/api/managers/{ids['a']}/products").json()
    assert products[0]["code"] == "FILE001"
    assert [share["name"] for share in products[0]["shares"]] == ["A", "B"]


def test_manual_completion_has_actor_and_preserves_original(env):
    app, client, ids = env
    login(client)
    p = product(client, ids["a"])
    doc = client.post(
        f"/api/managers/{ids['a']}/documents",
        files={"file": ("unknown.pdf", b"%PDF-not-a-real-layout")},
    ).json()
    run_once(app.state.factory, app.state.settings)
    issue = client.get(f"/api/managers/{ids['a']}/tasks").json()[0]
    result = client.post(
        f"/api/tasks/{issue['id']}/complete-material",
        json={
            "revision": issue["revision"],
            "reason": "已人工确认原件全部净值信息",
            "complete_material": True,
            "records": [nav_data(p)],
        },
    )
    assert result.status_code == 200, result.text
    with app.state.factory() as db:
        r = db.get(NavRecord, result.json()["record_ids"][0])
        assert (
            r.source == "manual"
            and r.actor_id == ids["ops"]
            and r.document_id == doc["id"]
        )
    assert (
        client.get(f"/api/documents/{doc['id']}/download").content
        == b"%PDF-not-a-real-layout"
    )


def test_invalid_nav_not_effective_and_cannot_be_waived(env):
    _, client, ids = env
    login(client)
    p = product(client, ids["a"])
    r = client.post(f"/api/managers/{ids['a']}/nav", json=nav_data(p, "-1")).json()
    issue = client.get(f"/api/managers/{ids['a']}/tasks").json()[0]
    assert (
        client.post(
            f"/api/tasks/{issue['id']}/resolve",
            json={
                "record_id": r["id"],
                "revision": issue["revision"],
                "reason": "真实情况",
            },
        ).status_code
        == 422
    )
    history = client.get(
        f"/api/products/{p['id']}/nav", params={"share_id": p["shares"][0]["id"]}
    ).json()
    assert history["effective"] == []
    assert (
        client.post(
            f"/api/managers/{ids['a']}/nav", json=nav_data(p, "1.12345678901")
        ).status_code
        == 422
    )


def test_missing_receipt_and_parse_are_independent(env):
    app, client, ids = env
    login(client)
    p = product(client, ids["a"])
    with app.state.factory.begin() as db:
        refresh_missing(
            db, ids["a"], at=datetime(2026, 8, 31, 13, tzinfo=ZoneInfo("Asia/Shanghai"))
        )
        refresh_missing(
            db, ids["a"], at=datetime(2026, 8, 31, 13, tzinfo=ZoneInfo("Asia/Shanghai"))
        )
    issues = client.get(f"/api/managers/{ids['a']}/tasks").json()
    assert len(issues) == 1 and issues[0]["valuation_date"] == "2026-08-28"
    client.post(f"/api/managers/{ids['a']}/nav", json=nav_data(p, "-1"))
    issues = client.get(f"/api/managers/{ids['a']}/tasks").json()
    assert next(i for i in issues if i["kind"] == "missing")["status"] == "resolved"
    assert next(i for i in issues if i["kind"] == "validation")["status"] == "open"


def test_product_only_reader_cannot_read_mixed_archives(env):
    app, client, ids = env
    login(client)
    p = product(client, ids["a"])
    product(client, ids["a"], "OTHER")
    doc = client.post(
        f"/api/managers/{ids['a']}/documents",
        files={"file": ("mixed.csv", b"mixed-content")},
    ).json()
    with app.state.factory.begin() as db:
        db.add(ProductGrant(user_id=ids["fund"], product_id=p["id"]))
    login(client, "fund")
    assert len(client.get(f"/api/managers/{ids['a']}/products").json()) == 1
    assert client.get(f"/api/documents/{doc['id']}/download").status_code == 403
    assert client.get(f"/api/managers/{ids['a']}/documents").status_code == 403
    assert (
        client.post(f"/api/managers/{ids['a']}/nav", json=nav_data(p)).status_code
        == 403
    )


def test_membership_without_roles_keeps_shared_exception_access(env):
    app, client, ids = env
    login(client)
    p = product(client, ids["a"])
    client.post(f"/api/managers/{ids['a']}/nav", json=nav_data(p, "-1"))
    login(client)
    assert (
        client.put(
            f"/api/managers/{ids['a']}/members/{ids['colleague']}",
            json={"roles": [], "can_download": False, "product_ids": []},
        ).status_code
        == 200
    )
    assert (
        client.get(f"/api/managers/{ids['a']}/tasks").json()[0]["assignee_id"] is None
    )
    login(client, "colleague")
    assert client.get("/api/auth/me").json()["managers"][0]["id"] == ids["a"]
    assert client.get(f"/api/managers/{ids['a']}/tasks").status_code == 200


def test_mime_archives_original_and_deduplicates_uid_validity(env):
    app, _, ids = env
    msg = EmailMessage()
    msg["Subject"] = "测试净值材料"
    msg["From"] = "custodian@test.invalid"
    msg.set_content("原始正文")
    msg.add_attachment(b"a,b\n1,2", maintype="text", subtype="csv", filename="净值.csv")
    raw = msg.as_bytes()
    with app.state.factory.begin() as db:
        box = Mailbox(
            manager_id=ids["a"],
            label="test",
            env_prefix="MAIL_TEST",
            since="2026-08-01",
        )
        db.add(box)
        db.flush()
        first = ingest_message(db, app.state.settings, box, "1", "10", raw)
        assert ingest_message(db, app.state.settings, box, "1", "10", raw) == first
        assert ingest_message(db, app.state.settings, box, "2", "10", raw) == first
        assert len(list(db.scalars(select(Document)))) == 2
        assert len(list(db.scalars(select(ParseJob)))) == 1
        original = db.get(Document, first)
        assert (app.state.settings.storage / original.storage_key).read_bytes() == raw


def test_xlsx_explicit_header_parser():
    wb = Workbook()
    ws = wb.active
    ws.append(["产品代码", "份额类别", "估值日期", "单位净值"])
    ws.append(["F001", "A", datetime(2026, 8, 28), 1.2345])
    buf = io.BytesIO()
    wb.save(buf)
    result = parse("净值.xlsx", buf.getvalue())
    assert result["errors"] == []
    assert result["records"][0]["unit_nav"] == "1.2345"
    assert result["records"][0]["valuation_date"] == "2026-08-28"


def test_upload_empty_product_selection_and_duplicate_codes(env):
    app, client, ids = env
    login(client)
    product(client, ids["a"])
    duplicate = client.post(
        f"/api/managers/{ids['a']}/products",
        json={"code": "F001", "name": "duplicate", "shares": ["A"]},
    )
    assert duplicate.status_code == 409
    result = client.post(
        f"/api/managers/{ids['a']}/documents",
        data={"product_id": ""},
        files={
            "file": (
                "normal.csv",
                "产品代码,份额类别,估值日期,单位净值\nF001,A,2026-08-28,1.05".encode(),
            )
        },
    )
    assert result.status_code == 201, result.text
    run_once(app.state.factory, app.state.settings)
    assert (
        client.get(f"/api/managers/{ids['a']}/documents").json()[0]["job"]["status"]
        == "completed"
    )


def test_cross_license_raw_archive_and_admin_logs_are_not_granted(env):
    app, client, ids = env
    login(client)
    product(client, ids["a"])
    login(client, "otherops")
    assert client.get(f"/api/managers/{ids['a']}/products").status_code == 200
    for route in ["documents", "audit", "mailboxes"]:
        assert client.get(f"/api/managers/{ids['a']}/{route}").status_code == 403
    with app.state.factory() as db:
        from app.models import AuditEvent

        assert (
            db.scalar(
                select(AuditEvent).where(
                    AuditEvent.manager_id == ids["a"],
                    AuditEvent.actor_id == ids["otherops"],
                    AuditEvent.action == "manager.cross_read",
                )
            )
            is not None
        )


def test_admin_has_all_pages_and_business_operations(env):
    _, client, ids = env
    login(client)
    p = product(client, ids["a"])
    client.post(f"/api/managers/{ids['a']}/nav", json=nav_data(p, "-1"))
    login(client, "admin")
    assert client.get(f"/api/managers/{ids['a']}/tasks").status_code == 200
    assert client.get(f"/api/managers/{ids['a']}/documents").status_code == 200
    assert (
        client.post(f"/api/managers/{ids['a']}/nav", json=nav_data(p)).status_code
        == 201
    )
