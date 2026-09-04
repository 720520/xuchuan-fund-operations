from datetime import datetime, timezone
from email.message import EmailMessage

import pytest
from app.mail_sync import sync_mailbox
from app.models import Document, Mailbox
from conftest import login, nav_data, product
from sqlalchemy import select


def test_soft_rule_requires_reason_and_is_admin_managed(env):
    app, client, ids = env
    login(client)
    p = product(client, ids["a"])
    assert (
        client.put(
            f"/api/managers/{ids['a']}/rules", json={"max_nav_change": "0.05"}
        ).status_code
        == 200
    )
    client.post(
        f"/api/managers/{ids['a']}/nav", json=nav_data(p, "1", day="2026-08-27")
    )
    r = client.post(f"/api/managers/{ids['a']}/nav", json=nav_data(p, "1.1")).json()
    issue = client.get(f"/api/managers/{ids['a']}/tasks").json()[0]
    assert r["validation"][0]["overridable"] is True
    payload = {"record_id": r["id"], "revision": issue["revision"], "reason": ""}
    assert (
        client.post(f"/api/tasks/{issue['id']}/resolve", json=payload).status_code
        == 422
    )
    payload["reason"] = "核对托管原件，确认为真实波动"
    assert (
        client.post(f"/api/tasks/{issue['id']}/resolve", json=payload).status_code
        == 200
    )
    login(client, "colleague")
    assert (
        client.put(
            f"/api/managers/{ids['a']}/rules", json={"max_nav_change": None}
        ).status_code
        == 403
    )


def test_summary_and_admin_settings_do_not_leak_nav(env):
    _, client, ids = env
    login(client)
    p = product(client, ids["a"])
    client.post(f"/api/managers/{ids['a']}/nav", json=nav_data(p))
    summary = client.get(
        f"/api/managers/{ids['a']}/summary", params={"valuation_date": "2026-08-28"}
    ).json()
    assert summary["expected"] == summary["received"] == summary["confirmed"] == 1
    login(client, "admin")
    settings = client.get(f"/api/managers/{ids['a']}/product-settings").json()
    assert settings[0]["shares"][0]["latest"] is None
    assert (
        client.get(
            f"/api/products/{p['id']}/nav", params={"share_id": p["shares"][0]["id"]}
        ).status_code
        == 200
    )


@pytest.mark.parametrize("oversize", [False, True])
def test_imap_never_changes_read_flag_and_preserves_bytes(env, monkeypatch, oversize):
    app, _, ids = env
    msg = EmailMessage()
    msg["Subject"] = "脱敏测试邮件"
    msg["From"] = "test@example.invalid"
    msg.set_content("测试正文")
    raw = msg.as_bytes()
    calls = []

    class FakeIMAP:
        def __init__(self, host, **kw):
            assert kw["ssl"] is True

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def login(self, user, password):
            calls.append("login")

        def select_folder(self, folder, readonly=False):
            assert readonly is True
            calls.append("readonly")
            return {b"UIDVALIDITY": 123}

        def search(self, criteria):
            return [7, 8] if oversize else [7]

        def fetch(self, uids, fields):
            calls.append(fields)
            message_uid = uids[0]
            if fields == ["RFC822.SIZE", "INTERNALDATE"]:
                return {
                    message_uid: {
                        b"RFC822.SIZE": app.state.settings.max_upload + 1
                        if oversize and message_uid == 7
                        else len(raw),
                        b"INTERNALDATE": datetime(2026, 8, 31, tzinfo=timezone.utc),
                    }
                }
            assert fields == ["BODY.PEEK[]"]
            return {message_uid: {b"BODY[]": raw}}

    for suffix, value in [
        ("HOST", "imap.test.invalid"),
        ("USER", "test"),
        ("PASSWORD", "test-only"),
    ]:
        monkeypatch.setenv("MAIL_FAKE_" + suffix, value)
    with app.state.factory.begin() as db:
        box = Mailbox(
            manager_id=ids["a"],
            label="Fake",
            env_prefix="MAIL_FAKE",
            since="2026-08-01",
            enabled=True,
        )
        db.add(box)
        db.flush()
        box_id = box.id
    assert sync_mailbox(app.state.factory, app.state.settings, box_id, FakeIMAP) == 1
    assert sync_mailbox(app.state.factory, app.state.settings, box_id, FakeIMAP) == 0
    assert calls.count(["BODY.PEEK[]"]) == 1
    with app.state.factory() as db:
        doc = db.scalar(select(Document))
        assert (app.state.settings.storage / doc.storage_key).read_bytes() == raw
