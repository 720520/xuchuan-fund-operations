from datetime import datetime, timezone
from email.message import EmailMessage

from app.mail_sync import sync_mailbox
from app.mailbox_security import decrypt_password
from app.models import Document, Mailbox, MailReceipt
from conftest import login
from sqlalchemy import select


def payload(
    username="operations@example.invalid", password="authorization code with spaces"
):
    return {
        "label": "运营邮箱",
        "host": "imap.example.invalid",
        "port": 993,
        "tls": "ssl",
        "username": username,
        "password": password,
        "since": "2000-01-01",
        "all_folders": True,
        "send_id": False,
        "enabled": True,
    }


def test_admin_manages_multiple_encrypted_mailboxes(env, monkeypatch):
    app, client, ids = env
    calls = []
    monkeypatch.setattr(
        "app.main.test_connection",
        lambda config: calls.append(config.copy()) or ["INBOX", "Archive"],
    )
    login(client)
    first = client.post(f"/api/managers/{ids['a']}/mailboxes", json=payload())
    assert first.status_code == 201, first.text
    second = client.post(
        f"/api/managers/{ids['a']}/mailboxes",
        json=payload("second@example.invalid", "second-test-authorization"),
    )
    assert second.status_code == 201
    assert len(calls) == 2
    with app.state.factory() as db:
        boxes = list(db.scalars(select(Mailbox).order_by(Mailbox.username)))
        assert len(boxes) == 2
        assert boxes[0].credential_ciphertext != "authorization code with spaces"
        assert (
            decrypt_password(app.state.settings, boxes[0])
            == "authorization code with spaces"
        )
        assert app.state.settings.mail_key_file.stat().st_mode & 0o777 == 0o600
        assert app.state.settings.mail_key_file.parent.stat().st_mode & 0o777 == 0o700
    listed = client.get(f"/api/managers/{ids['a']}/mailboxes").json()
    assert len(listed) == 2
    assert listed[0]["credential_configured"] is True
    assert "credential_ciphertext" not in listed[0]
    assert "env_prefix" not in listed[0]
    assert "password" not in str(listed)
    duplicate = client.post(f"/api/managers/{ids['a']}/mailboxes", json=payload())
    assert duplicate.status_code == 409
    assert len(calls) == 2  # Duplicate is rejected without another remote login.


def test_non_admin_cannot_create_update_or_test_mailbox(env, monkeypatch):
    _, client, ids = env
    monkeypatch.setattr(
        "app.main.test_connection",
        lambda _: (_ for _ in ()).throw(AssertionError("must not connect")),
    )
    login(client, "colleague")
    assert (
        client.post(f"/api/managers/{ids['a']}/mailboxes", json=payload()).status_code
        == 403
    )
    assert (
        client.put(
            f"/api/managers/{ids['a']}/mailboxes/unknown",
            json={**payload(), "password": None},
        ).status_code
        == 403
    )
    assert (
        client.post(f"/api/managers/{ids['a']}/mailboxes/unknown/test").status_code
        == 403
    )


def test_failed_connection_does_not_save_mailbox_or_key(env, monkeypatch):
    app, client, ids = env
    monkeypatch.setattr(
        "app.main.test_connection",
        lambda _: (_ for _ in ()).throw(RuntimeError("remote detail must be hidden")),
    )
    login(client)
    response = client.post(f"/api/managers/{ids['a']}/mailboxes", json=payload())
    assert response.status_code == 422
    assert "remote detail" not in response.text
    with app.state.factory() as db:
        assert db.scalar(select(Mailbox)) is None
    assert not app.state.settings.mail_key_file.exists()


def test_edit_preserves_or_replaces_secret_and_disable_is_offline(env, monkeypatch):
    app, client, ids = env
    calls = []
    monkeypatch.setattr(
        "app.main.test_connection",
        lambda config: calls.append(config.copy()) or ["INBOX"],
    )
    login(client)
    created = client.post(f"/api/managers/{ids['a']}/mailboxes", json=payload()).json()
    box_id = created["id"]
    update = {**payload(), "label": "已修改", "password": None, "enabled": False}
    assert (
        client.put(
            f"/api/managers/{ids['a']}/mailboxes/{box_id}", json=update
        ).status_code
        == 200
    )
    assert len(calls) == 1  # Disabling must work even while the remote server is down.
    with app.state.factory() as db:
        box = db.get(Mailbox, box_id)
        assert (
            decrypt_password(app.state.settings, box)
            == "authorization code with spaces"
        )
        assert box.enabled is False
    update.update(password="new authorization", enabled=True)
    assert (
        client.put(
            f"/api/managers/{ids['a']}/mailboxes/{box_id}", json=update
        ).status_code
        == 200
    )
    with app.state.factory() as db:
        assert (
            decrypt_password(app.state.settings, db.get(Mailbox, box_id))
            == "new authorization"
        )
    tested = client.post(f"/api/managers/{ids['a']}/mailboxes/{box_id}/test")
    assert tested.status_code == 200 and tested.json()["folders"] == ["INBOX"]
    assert len(calls) == 3


def test_all_folder_sync_is_readonly_and_folder_uid_aware(env, monkeypatch):
    app, _, ids = env
    message = EmailMessage()
    message["Subject"] = "跨文件夹同一原件"
    message.set_content("测试")
    raw = message.as_bytes()
    calls = []

    class FakeIMAP:
        def __init__(self, host, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def login(self, *_):
            pass

        def list_folders(self):
            return [((), "/", "INBOX"), ((), "/", "Archive")]

        def select_folder(self, folder, readonly=False):
            assert readonly is True
            calls.append((folder, "readonly"))
            return {b"UIDVALIDITY": 7}

        def search(self, criteria):
            return [1]

        def fetch(self, uids, fields):
            if fields == ["RFC822.SIZE", "INTERNALDATE"]:
                return {
                    1: {
                        b"RFC822.SIZE": len(raw),
                        b"INTERNALDATE": datetime(2026, 9, 1, tzinfo=timezone.utc),
                    }
                }
            assert fields == ["BODY.PEEK[]"]
            return {1: {b"BODY[]": raw}}

    for suffix, value in [
        ("HOST", "imap.test.invalid"),
        ("USER", "test"),
        ("PASSWORD", "test-only"),
    ]:
        monkeypatch.setenv("MAIL_ALL_" + suffix, value)
    with app.state.factory.begin() as db:
        box = Mailbox(
            manager_id=ids["a"],
            label="all",
            env_prefix="MAIL_ALL",
            since="2000-01-01",
            enabled=True,
            all_folders=True,
        )
        db.add(box)
        db.flush()
        box_id = box.id
    assert sync_mailbox(app.state.factory, app.state.settings, box_id, FakeIMAP) == 2
    assert sync_mailbox(app.state.factory, app.state.settings, box_id, FakeIMAP) == 0
    assert calls == [("INBOX", "readonly"), ("Archive", "readonly")] * 2
    with app.state.factory() as db:
        assert len(list(db.scalars(select(MailReceipt)))) == 2
        assert len(list(db.scalars(select(Document)))) == 1
