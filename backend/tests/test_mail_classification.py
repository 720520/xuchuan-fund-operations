from email.message import EmailMessage

from sqlalchemy import select

from app.mail_classification import classify, classify_pending_mail
from app.mail_sync import ingest_message
from app.mailbox_security import selectable_folders
from app.models import Document, MailAction, MailItem, Mailbox, Membership, ParseJob, User
from app.security import password_hash
from app.services import archive, task
from conftest import PASSWORD, login


def message(subject, body="请查收。", attachment="材料.xlsx"):
    value = EmailMessage()
    value["Subject"] = subject
    value["From"] = "custodian@example.invalid"
    value.set_content(body)
    if attachment:
        value.add_attachment(
            b"test-only",
            maintype="application",
            subtype="octet-stream",
            filename=attachment,
        )
    return value


def mailbox(db, manager_id):
    value = Mailbox(
        manager_id=manager_id,
        label="运营邮箱",
        env_prefix="MAIL_CLASSIFY_TEST",
        since="2026-01-01",
        enabled=True,
    )
    db.add(value)
    db.flush()
    return value


def test_rules_separate_nav_tasks_and_unknown_mail():
    assert classify(message("每日估值表")).category == "nav_valuation"
    assert classify(message("1940产品20260907"), "基金估值表").category == "nav_valuation"
    risk = classify(message("投资监督违规提醒", "请核查相关交易。"))
    assert (risk.handling_mode, risk.priority) == ("task", "high")
    assert classify(message("普通通知", attachment="说明.pdf")).handling_mode == "pending"


def test_html_style_and_script_are_not_shown_in_mail_excerpt(env):
    app, _, ids = env
    value = EmailMessage()
    value["Subject"] = "普通业务说明"
    value["From"] = "custodian@example.invalid"
    value.set_content("请查看 HTML 邮件。")
    value.add_alternative(
        "<html><head><style>.x{width:9999px}</style>"
        "<script>alert('hidden')</script></head><body>"
        "<p>测试产品F001正文内容为2026年9月9日</p></body></html>",
        subtype="html",
    )
    with app.state.factory.begin() as db:
        box = mailbox(db, ids["a"])
        document_id = ingest_message(
            db, app.state.settings, box, "1", "html", value.as_bytes()
        )
    with app.state.factory() as db:
        item = db.scalar(select(MailItem).where(MailItem.document_id == document_id))
        assert "测试产品F001正文内容" in item.excerpt
        assert "width:9999px" not in item.excerpt
        assert "alert('hidden')" not in item.excerpt


def test_mail_detail_returns_complete_safe_body_headers_and_attachments(env):
    app, client, ids = env
    value = EmailMessage()
    value["Subject"] = "申购确认单"
    value["From"] = "custodian@example.invalid"
    value["To"] = "operations@example.invalid"
    value["Cc"] = "review@example.invalid"
    value["Date"] = "Thu, 10 Sep 2026 10:20:00 +0800"
    value.set_content("纯文本备用正文")
    value.add_alternative(
        "<html><head><meta charset='utf-8'><style>"
        ".warp{max-width:740px}.header{background:#19223F;display:flex;align-items:center;"
        "justify-content:space-between}.remote{background:url(https://tracker.example.invalid/pixel.gif)}"
        "</style></head><body><div class='warp'><div class='header'>待办事项</div>"
        "<table style='background-color:#172448;width:80%'>"
        "<tr><td id='main-content' style='color:#ff5a00' onclick='should_not_run()'><h2>正文开始</h2><p>"
        + "完整内容" * 6000
        + "</p><p>正文结束</p></td></tr></table></div>"
        "<img src='https://tracker.example.invalid/pixel.gif'>"
        "<script>should_not_run()</script></body></html>",
        subtype="html",
    )
    value.add_attachment(
        b"confirmation",
        maintype="application",
        subtype="octet-stream",
        filename="申购确认单.xlsx",
    )
    with app.state.factory.begin() as db:
        box = mailbox(db, ids["a"])
        document_id = ingest_message(
            db, app.state.settings, box, "1", "detail", value.as_bytes()
        )
        item = db.scalar(select(MailItem).where(MailItem.document_id == document_id))
        item_id = item.id

    login(client)
    response = client.get(f"/api/mail-items/{item_id}")
    assert response.status_code == 200
    detail = response.json()
    assert detail["subject"] == "申购确认单"
    assert detail["to"] == "operations@example.invalid"
    assert detail["cc"] == "review@example.invalid"
    assert "正文开始" in detail["body"]
    assert detail["body"].endswith("正文结束")
    assert "should_not_run" not in detail["body"]
    assert len(detail["body"]) > 20000
    assert "<table" in detail["body_html"]
    assert "background-color: #172448" in detail["body_html"]
    assert "color: #ff5a00" in detail["body_html"]
    assert 'class="warp"' in detail["body_html"]
    assert 'id="main-content"' in detail["body_html"]
    assert ".header{background: #19223F; display: flex; align-items: center; justify-content: space-between}" in detail["body_html"]
    assert "完整内容" in detail["body_html"]
    assert "should_not_run" not in detail["body_html"]
    assert "tracker.example.invalid" not in detail["body_html"]
    assert "default-src 'none'" in detail["body_html"]
    assert 'id="xuchuan-mail-scroll"' in detail["body_html"]
    assert "height:100vh" in detail["body_html"]
    assert "overflow:auto!important" in detail["body_html"]
    assert [item["filename"] for item in detail["attachments"]] == ["申购确认单.xlsx"]
    assert detail["sources"][0]["mailbox"] == "运营邮箱"

    client.cookies.clear()
    login(client, "fund")
    assert client.get(f"/api/mail-items/{item_id}").status_code == 403


def test_exception_links_attachment_back_to_original_mail(env):
    app, client, ids = env
    with app.state.factory.begin() as db:
        box = mailbox(db, ids["a"])
        original_id = ingest_message(
            db,
            app.state.settings,
            box,
            "1",
            "exception-source",
            message("需人工核查的业务材料", attachment="核查材料.pdf").as_bytes(),
        )
        mail_item = db.scalar(
            select(MailItem).where(MailItem.document_id == original_id)
        )
        attachment_id = db.scalar(
            select(Document.id).where(Document.parent_id == original_id)
        )
        issue = task(
            db,
            ids["a"],
            "parse",
            "parse:mail-link-test",
            {"document_id": attachment_id, "errors": [{"reason": "需要人工核查"}]},
        )
        issue_id = issue.id
        mail_item_id = mail_item.id

    login(client)
    tasks = client.get(f"/api/managers/{ids['a']}/tasks").json()
    linked = next(item for item in tasks if item["id"] == issue_id)
    assert linked["mail_item_id"] == mail_item_id
    assert linked["mail_item_category"] == "unknown"

    exact = client.get(
        f"/api/managers/{ids['a']}/mail-items",
        params={"paginated": True, "item_id": mail_item_id},
    ).json()
    assert exact["total"] == 1
    assert exact["items"][0]["id"] == mail_item_id


def test_investor_mail_original_and_attachments_require_investor_permission(env):
    app, client, ids = env
    with app.state.factory.begin() as db:
        box = mailbox(db, ids["a"])
        original_id = ingest_message(
            db,
            app.state.settings,
            box,
            "1",
            "investor-sensitive",
            message("申购确认单", attachment="申购确认单.xlsx").as_bytes(),
        )
        item = db.scalar(select(MailItem).where(MailItem.document_id == original_id))
        assert item.category == "investor_redemption"
        attachment_id = db.scalar(
            select(Document.id).where(Document.parent_id == original_id)
        )
        viewer = User(
            email="mail-viewer@test.invalid",
            name="mail viewer",
            password_hash=password_hash(PASSWORD),
        )
        db.add(viewer)
        db.flush()
        db.add(
            Membership(
                user_id=viewer.id,
                manager_id=ids["a"],
                roles=["group_viewer"],
                can_download=True,
            )
        )

    login(client, "mail-viewer")
    assert client.get(f"/api/managers/{ids['a']}/mail-items").json() == []
    visible_document_ids = {
        document["id"]
        for document in client.get(f"/api/managers/{ids['a']}/documents").json()
    }
    assert original_id not in visible_document_ids
    assert attachment_id not in visible_document_ids
    paginated = client.get(
        f"/api/managers/{ids['a']}/documents",
        params={"paginated": "true", "q": "申购确认单"},
    ).json()
    assert paginated["total"] == 0
    assert paginated["items"] == []
    assert client.get(f"/api/documents/{original_id}/download").status_code == 403
    assert client.get(f"/api/documents/{attachment_id}/download").status_code == 403


def test_ingest_routes_only_nav_attachments_and_completes_mail_action(env):
    app, client, ids = env
    with app.state.factory.begin() as db:
        box = mailbox(db, ids["a"])
        nav_id = ingest_message(
            db, app.state.settings, box, "1", "1", message("产品估值表").as_bytes()
        )
        security_id = ingest_message(
            db,
            app.state.settings,
            box,
            "1",
            "2",
            message("新设备登录提醒", "如非本人请核查。" ).as_bytes(),
        )
    with app.state.factory() as db:
        nav_item = db.scalar(select(MailItem).where(MailItem.document_id == nav_id))
        security_item = db.scalar(
            select(MailItem).where(MailItem.document_id == security_id)
        )
        nav_attachment = db.scalar(
            select(Document).where(Document.parent_id == nav_id)
        )
        security_attachment = db.scalar(
            select(Document).where(Document.parent_id == security_id)
        )
        assert nav_item.category == "nav_valuation"
        assert db.scalar(
            select(ParseJob).where(ParseJob.document_id == nav_attachment.id)
        )
        assert security_item.category == "security"
        assert security_item.excerpt.startswith("安全提醒内容已限制展示")
        assert db.scalar(
            select(ParseJob).where(ParseJob.document_id == security_attachment.id)
        ) is None
        action = db.scalar(
            select(MailAction).where(MailAction.mail_item_id == security_item.id)
        )
        action_id, revision = action.id, action.revision

    login(client)
    listed = client.get(f"/api/managers/{ids['a']}/mail-items")
    assert listed.status_code == 200
    assert len(listed.json()) == 2
    completed = client.post(
        f"/api/mail-actions/{action_id}/complete",
        json={"revision": revision, "reason": "已核查，确认为本人登录"},
    )
    assert completed.status_code == 200


def test_backfill_skips_previously_queued_non_nav_attachment(env):
    app, client, ids = env
    raw = message("普通业务说明", attachment="说明.pdf").as_bytes()
    with app.state.factory.begin() as db:
        original = archive(
            db, app.state.settings, ids["a"], "old.eml", raw, "email"
        )
        child = archive(
            db,
            app.state.settings,
            ids["a"],
            "说明.pdf",
            b"not-a-nav-document",
            "email",
            parent_id=original.id,
        )
        db.add(ParseJob(manager_id=ids["a"], document_id=child.id))
        child_id = child.id
    assert classify_pending_mail(app.state.factory, app.state.settings) == 1
    with app.state.factory() as db:
        job = db.scalar(select(ParseJob).where(ParseJob.document_id == child_id))
        assert job.status == "skipped"
        assert "不是净值或估值" in job.result["reason"]
        item = db.scalar(select(MailItem).where(MailItem.document_id == original.id))
        item_id, revision = item.id, item.revision
    login(client)
    corrected = client.put(
        f"/api/mail-items/{item_id}/classification",
        json={
            "revision": revision,
            "category": "nav_valuation",
            "handling_mode": "receipt",
            "suggested_action": None,
        },
    )
    assert corrected.status_code == 200
    with app.state.factory() as db:
        job = db.scalar(select(ParseJob).where(ParseJob.document_id == child_id))
        assert job.status == "queued"


def test_daily_folder_scan_excludes_special_mail_folders():
    class Fake:
        def list_folders(self):
            return [
                (("\\Inbox",), "/", "INBOX"),
                (("\\Sent",), "/", "已发送"),
                ((), "/", "基金估值表"),
                ((), "/", "垃圾邮件"),
            ]

    assert selectable_folders(Fake()) == ["INBOX", "已发送", "基金估值表", "垃圾邮件"]
    assert selectable_folders(Fake(), exclude_special=True) == ["INBOX", "基金估值表"]


def test_mailbox_paging_includes_shared_mail_and_checks_scope(env):
    app, client, ids = env
    with app.state.factory.begin() as db:
        first = mailbox(db, ids['a'])
        second = Mailbox(manager_id=ids['a'], label='净值邮箱', env_prefix='SECOND', since='2026-01-01', enabled=True)
        foreign = Mailbox(manager_id=ids['b'], label='其他牌照', env_prefix='FOREIGN', since='2026-01-01', enabled=True)
        db.add(foreign)
        db.add(second)
        db.flush()
        first_id, second_id, foreign_id = first.id, second.id, foreign.id
        raw = message('共享业务通知', attachment=None).as_bytes()
        shared = ingest_message(db, app.state.settings, first, '1', '1', raw)
        ingest_message(db, app.state.settings, second, '1', '1', raw)
        ingest_message(db, app.state.settings, first, '1', '2', message('独有业务通知', attachment=None).as_bytes())
    login(client)
    url = f'/api/managers/{ids["a"]}/mail-items'
    page = client.get(url, params={'paginated': True, 'mailbox_id': first_id, 'limit': 1}).json()
    assert page['total'] == 2 and len(page['items']) == 1
    later = client.get(url, params={'paginated': True, 'mailbox_id': first_id, 'limit': 1, 'offset': 1}).json()
    assert page['items'][0]['id'] != later['items'][0]['id']
    other = client.get(url, params={'paginated': True, 'mailbox_id': second_id}).json()
    assert other['total'] == 1
    assert other['items'][0]['document_id'] == shared
    assert {s['mailbox_id'] for s in other['items'][0]['sources']} == {first_id, second_id}
    searched = client.get(url, params={'paginated': True, 'mailbox_id': first_id, 'q': '独有'}).json()
    assert searched['total'] == 1
    assert client.get(url, params={'mailbox_id': foreign_id}).status_code == 404
    assert client.get(url, params={'paginated': True, 'offset': -1}).status_code == 422
    assert client.get(url, params={'paginated': True, 'offset': 10}).json()['items'] == []
