from io import BytesIO

from app.mailbox_security import decrypt_sensitive_value
from app.models import (
    AuditEvent,
    Document,
    DocumentMaterial,
    DocumentMaterialInvestor,
    DocumentMaterialProduct,
    ExceptionTask,
    Investor,
    InvestorBankAccount,
    InvestorBankAccountProduct,
    InvestorPositionSnapshot,
    MailAction,
    MailItem,
    Membership,
    User,
)
from app.security import password_hash
from app.services import archive, import_investor_position_documents
from conftest import PASSWORD, login, product
from openpyxl import Workbook
from sqlalchemy import select


def investor_payload(product_ids, **changes):
    return {
        "revision": 0,
        "investor_type": "individual",
        "display_name": "样本投资者",
        "status": "pending",
        "source": "directory_reference",
        "product_ids": product_ids,
        "notes": "仅按待整理目录建立索引，身份待核对",
        **changes,
    }


def test_lightweight_investor_crud_and_multi_product_relationship(env):
    app, client, ids = env
    login(client)
    first = product(client, ids["a"], "INV001")
    second = product(client, ids["a"], "INV002")

    created = client.post(
        f"/api/managers/{ids['a']}/investors",
        json=investor_payload([first["id"], second["id"]]),
    )
    assert created.status_code == 201, created.text
    investor = created.json()
    assert investor["display_name"] == "样本投资者"
    assert investor["revision"] == 1
    assert set(investor["product_ids"]) == {first["id"], second["id"]}
    assert investor["material_count"] == 0

    listed = client.get(f"/api/managers/{ids['a']}/investors")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [investor["id"]]

    updated_payload = investor_payload(
        [second["id"]],
        revision=1,
        display_name="样本投资者（已核对）",
        status="confirmed",
        source="material",
    )
    updated = client.put(f"/api/investors/{investor['id']}", json=updated_payload)
    assert updated.status_code == 200, updated.text
    assert updated.json()["revision"] == 2
    assert updated.json()["product_ids"] == [second["id"]]
    assert client.put(f"/api/investors/{investor['id']}", json=updated_payload).status_code == 409

    login(client, "otherops")
    other = product(client, ids["b"], "INV003")
    login(client)
    cross_scope = client.put(
        f"/api/investors/{investor['id']}",
        json=investor_payload([other["id"]], revision=2),
    )
    assert cross_scope.status_code == 422

    with app.state.factory() as db:
        saved = db.get(Investor, investor["id"])
        assert saved.display_name == "样本投资者（已核对）"
        events = list(
            db.scalars(
                select(AuditEvent).where(AuditEvent.object_id == investor["id"])
            )
        )
        assert [event.action for event in events] == [
            "investor.created",
            "investor.updated",
        ]
        assert "样本投资者" not in str([event.details for event in events])


def test_sensitive_investor_material_is_separately_authorized(env):
    app, client, ids = env
    login(client)
    own_product = product(client, ids["a"], "INV004")
    investor = client.post(
        f"/api/managers/{ids['a']}/investors",
        json=investor_payload([own_product["id"]]),
    ).json()
    uploaded = client.post(
        f"/api/managers/{ids['a']}/documents",
        data={"product_id": own_product["id"]},
        files={"file": ("投资者信息表.pdf", b"sensitive-original", "application/pdf")},
    ).json()
    organization = {
        "revision": 0,
        "category": "investor_qualification",
        "material_type": "investor_information_form",
        "title": "投资者信息表",
        "business_date": None,
        "period_start": None,
        "period_end": None,
        "product_ids": [own_product["id"]],
        "investor_ids": [investor["id"]],
        "sensitivity": "investor_sensitive",
        "notes": "已核对目录归属",
        "confirmed": True,
    }
    organized = client.put(
        f"/api/documents/{uploaded['id']}/material", json=organization
    )
    assert organized.status_code == 200, organized.text
    assert organized.json()["investor_ids"] == [investor["id"]]
    assert organized.json()["sensitivity"] == "investor_sensitive"
    assert organized.json()["material_type"] == "investor_information_form"
    assert client.get(f"/api/managers/{ids['a']}/investors").json()[0]["material_count"] == 1

    sourced = client.put(
        f"/api/investors/{investor['id']}",
        json=investor_payload(
            [own_product["id"]],
            revision=1,
            profile_source_document_id=uploaded["id"],
        ),
    )
    assert sourced.status_code == 200, sourced.text
    assert sourced.json()["profile_source_document_id"] == uploaded["id"]

    with app.state.factory.begin() as db:
        viewer = User(
            email="viewer@test.invalid",
            name="viewer",
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

    login(client, "viewer")
    assert client.get(f"/api/managers/{ids['a']}/investors").status_code == 403
    assert client.get(f"/api/managers/{ids['a']}/documents").json() == []
    paginated = client.get(
        f"/api/managers/{ids['a']}/documents",
        params={"paginated": "true", "q": "投资者信息表"},
    ).json()
    assert paginated["total"] == 0
    assert paginated["items"] == []
    assert client.get(f"/api/documents/{uploaded['id']}/download").status_code == 403


def test_investor_material_requires_sensitive_mark(env):
    _, client, ids = env
    login(client)
    own_product = product(client, ids["a"], "INV005")
    investor = client.post(
        f"/api/managers/{ids['a']}/investors",
        json=investor_payload([own_product["id"]]),
    ).json()
    uploaded = client.post(
        f"/api/managers/{ids['a']}/documents",
        files={"file": ("认申购单.pdf", b"subscription", "application/pdf")},
    ).json()
    response = client.put(
        f"/api/documents/{uploaded['id']}/material",
        json={
            "revision": 0,
            "category": "subscription_redemption",
            "title": "认申购单",
            "business_date": None,
            "period_start": None,
            "period_end": None,
            "product_ids": [own_product["id"]],
            "investor_ids": [investor["id"]],
            "sensitivity": "standard",
            "notes": "",
            "confirmed": True,
        },
    )
    assert response.status_code == 422
    assert "敏感资料" in response.text


def test_upload_can_stage_sensitive_material_for_investor(env):
    app, client, ids = env
    login(client)
    own_product = product(client, ids["a"], "INV006")
    investor = client.post(
        f"/api/managers/{ids['a']}/investors",
        json=investor_payload([own_product["id"]]),
    ).json()

    uploaded = client.post(
        f"/api/managers/{ids['a']}/documents",
        data={"product_id": own_product["id"], "investor_id": investor["id"]},
        files={"file": ("风险测评.pdf", b"sensitive-original", "application/pdf")},
    )
    assert uploaded.status_code == 201, uploaded.text
    document_id = uploaded.json()["id"]

    listed = client.get(f"/api/managers/{ids['a']}/documents").json()
    staged = next(item for item in listed if item["id"] == document_id)
    assert staged["material_status"] == "pending"
    assert staged["sensitivity"] == "investor_sensitive"
    assert staged["investor_ids"] == [investor["id"]]
    assert staged["product_ids"] == [own_product["id"]]
    assert staged["job"]["status"] == "skipped"

    with app.state.factory.begin() as db:
        viewer = User(
            email="staged-viewer@test.invalid",
            name="staged viewer",
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

    login(client, "staged-viewer")
    assert all(
        item["id"] != document_id
        for item in client.get(f"/api/managers/{ids['a']}/documents").json()
    )
    assert client.get(f"/api/documents/{document_id}/download").status_code == 403


def test_structured_profile_and_bank_accounts_encrypt_sensitive_numbers(env):
    app, client, ids = env
    login(client)
    first = product(client, ids["a"], "INV007")
    second = product(client, ids["a"], "INV008")
    certificate_number = "340104199510274539"
    created = client.post(
        f"/api/managers/{ids['a']}/investors",
        json=investor_payload(
            [first["id"], second["id"]],
            suitability_class="ordinary",
            certificate_type="identity_card",
            certificate_number=certificate_number,
            certificate_valid_until="2045-08-11",
            nationality_or_region="中国",
            contact_email="sample@example.invalid",
            contact_phone="13800000000",
            specific_object_status="confirmed",
            specific_object_confirmed_at="2026-09-10",
            risk_level="C4",
            risk_assessed_at="2026-09-10",
            risk_expires_at="2027-09-09",
            qualified_material_status="valid",
            qualified_material_from="2026-09-10",
            qualified_material_until="2027-09-09",
        ),
    )
    assert created.status_code == 201, created.text
    investor = created.json()
    assert investor["certificate_number_masked"] == "3401********4539"
    assert "certificate_number_ciphertext" not in investor
    assert certificate_number not in created.text
    assert investor["risk_level"] == "C4"

    with app.state.factory() as db:
        saved = db.get(Investor, investor["id"])
        original_ciphertext = saved.certificate_number_ciphertext
        assert original_ciphertext and certificate_number not in original_ciphertext
        assert decrypt_sensitive_value(
            app.state.settings,
            "investor_certificate",
            saved.id,
            original_ciphertext,
        ) == certificate_number

    account_number = "6214832612689641"
    account_response = client.post(
        f"/api/investors/{investor['id']}/bank-accounts",
        json={
            "revision": 0,
            "account_name": "样本投资者",
            "account_number": account_number,
            "bank_name": "招商银行",
            "branch_name": "上海分行",
            "currency": "cny",
            "status": "active",
            "source_document_id": None,
            "product_ids": [first["id"], second["id"]],
        },
    )
    assert account_response.status_code == 201, account_response.text
    account = account_response.json()
    assert account["account_number_masked"] == "6214********9641"
    assert account["currency"] == "CNY"
    assert set(account["product_ids"]) == {first["id"], second["id"]}
    assert "account_number_ciphertext" not in account
    assert account_number not in account_response.text

    with app.state.factory() as db:
        saved_account = db.get(InvestorBankAccount, account["id"])
        ciphertext = saved_account.account_number_ciphertext
        assert account_number not in ciphertext
        assert decrypt_sensitive_value(
            app.state.settings,
            "investor_bank_account",
            saved_account.id,
            ciphertext,
        ) == account_number
        assert set(
            db.scalars(
                select(InvestorBankAccountProduct.product_id).where(
                    InvestorBankAccountProduct.bank_account_id == saved_account.id
                )
            )
        ) == {first["id"], second["id"]}

    account_update = client.put(
        f"/api/investor-bank-accounts/{account['id']}",
        json={
            "revision": 1,
            "account_name": "样本投资者",
            "account_number": None,
            "bank_name": "招商银行",
            "branch_name": "上海分行营业部",
            "currency": "CNY",
            "status": "inactive",
            "source_document_id": None,
            "product_ids": [second["id"]],
        },
    )
    assert account_update.status_code == 200, account_update.text
    assert account_update.json()["account_number_masked"] == "6214********9641"
    assert account_update.json()["status"] == "inactive"
    assert account_update.json()["product_ids"] == [second["id"]]

    listed = client.get(f"/api/managers/{ids['a']}/investors").json()
    listed_investor = next(item for item in listed if item["id"] == investor["id"])
    assert listed_investor["bank_accounts"][0]["id"] == account["id"]
    assert account_number not in str(listed_investor)

    preserved = client.put(
        f"/api/investors/{investor['id']}",
        json=investor_payload(
            [first["id"]],
            revision=1,
            suitability_class="ordinary",
            certificate_type="identity_card",
            certificate_number=None,
            certificate_valid_until="2045-08-11",
        ),
    )
    assert preserved.status_code == 200, preserved.text
    assert preserved.json()["certificate_number_masked"] == "3401********4539"
    with app.state.factory() as db:
        assert db.get(Investor, investor["id"]).certificate_number_ciphertext == original_ciphertext


def test_share_events_require_confirmation_and_preserve_position_evidence(env):
    _, client, ids = env
    login(client)
    owned_product = product(client, ids["a"], "INV009")
    investor = client.post(
        f"/api/managers/{ids['a']}/investors",
        json=investor_payload([owned_product["id"]], status="confirmed"),
    ).json()

    notice = client.post(
        f"/api/investors/{investor['id']}/share-events",
        json={
            "product_id": owned_product["id"],
            "share_id": owned_product["shares"][0]["id"],
            "event_type": "subscription",
            "evidence_stage": "notice",
            "application_date": "2026-09-14",
            "requested_amount": "100000.00",
            "notes": "仅收到申请通知",
        },
    )
    assert notice.status_code == 201, notice.text
    assert notice.json()["status"] == "archived"

    invalid_redemption = client.post(
        f"/api/investors/{investor['id']}/share-events",
        json={
            "product_id": owned_product["id"],
            "event_type": "redemption",
            "evidence_stage": "application",
            "units_delta": "100",
        },
    )
    assert invalid_redemption.status_code == 422

    confirmation = client.post(
        f"/api/investors/{investor['id']}/share-events",
        json={
            "product_id": owned_product["id"],
            "share_id": owned_product["shares"][0]["id"],
            "event_type": "subscription",
            "evidence_stage": "confirmation",
            "confirmation_date": "2026-09-15",
            "effective_date": "2026-09-15",
            "confirmed_amount": "100000.00",
            "units_delta": "95238.095238",
            "unit_nav": "1.05000000",
            "balance_after": "95238.095238",
            "business_ref": "ORDER-20260915-001",
            "notes": "托管确认单",
        },
    )
    assert confirmation.status_code == 201, confirmation.text
    event = confirmation.json()
    assert event["status"] == "pending"
    tasks = client.get(f"/api/managers/{ids['a']}/tasks").json()
    share_task = next(item for item in tasks if item["kind"] == "investor_share")
    assert share_task["investor_name"] == investor["display_name"]
    assert share_task["payload"]["reason"] == "source_mail_missing"
    before = client.get(f"/api/investors/{investor['id']}/share-events").json()
    assert before["positions"] == []

    confirmed = client.put(
        f"/api/investor-share-events/{event['id']}/status",
        json={"revision": 1, "status": "confirmed", "reason": "已与托管确认单核对"},
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["status"] == "confirmed"
    resolved = next(
        item
        for item in client.get(f"/api/managers/{ids['a']}/tasks").json()
        if item["id"] == share_task["id"]
    )
    assert resolved["status"] == "resolved"
    assert client.put(
        f"/api/investor-share-events/{event['id']}/status",
        json={"revision": 2, "status": "void", "reason": "尝试覆盖历史"},
    ).status_code == 409

    snapshot = client.post(
        f"/api/investors/{investor['id']}/position-snapshots",
        json={
            "product_id": owned_product["id"],
            "share_id": owned_product["shares"][0]["id"],
            "as_of_date": "2026-09-15",
            "units": "95238.095238",
            "notes": "托管持仓表",
        },
    )
    assert snapshot.status_code == 201, snapshot.text
    ledger = client.get(f"/api/investors/{investor['id']}/share-events").json()
    assert ledger["positions"][0]["confirmed_units"] == "95238.095238"
    assert ledger["positions"][0]["latest_snapshot_units"] == "95238.095238"
    assert ledger["positions"][0]["difference"] == "0.000000"
    assert [item["status"] for item in ledger["events"]] == ["confirmed", "archived"]

    duplicate = client.post(
        f"/api/investors/{investor['id']}/share-events",
        json={
            "product_id": owned_product["id"],
            "event_type": "subscription",
            "evidence_stage": "confirmation",
            "confirmation_date": "2026-09-15",
            "business_ref": "ORDER-20260915-001",
        },
    )
    assert duplicate.status_code == 409


def test_mail_confirmation_auto_posts_and_product_ledger_aggregates(env):
    app, client, ids = env
    login(client)
    owned_product = product(client, ids["a"], "INV010")
    investor = client.post(
        f"/api/managers/{ids['a']}/investors",
        json=investor_payload([owned_product["id"]], status="confirmed"),
    ).json()

    with app.state.factory.begin() as db:
        document = Document(
            manager_id=ids["a"],
            filename="investor-share-confirmation.eml",
            sha256="1" * 64,
            storage_key="test/investor-share-confirmation.eml",
            size=128,
            media_type="message/rfc822",
            source="email",
            metadata_json={},
        )
        db.add(document)
        db.flush()
        mail_item = MailItem(
            manager_id=ids["a"],
            document_id=document.id,
            category="investor_redemption",
            title="投资者份额确认",
            sender="custodian@example.invalid",
            business_date="2026-09-15",
            handling_mode="task",
            priority="normal",
            classification_source="rule",
            confidence=95,
            status="received",
            excerpt="确认后份额 120000.000000",
        )
        db.add(mail_item)
        db.flush()
        db.add(
            MailAction(
                manager_id=ids["a"],
                mail_item_id=mail_item.id,
                suggested_action="整理投资者份额",
            )
        )
        mail_item_id = mail_item.id

    created = client.post(
        f"/api/investors/{investor['id']}/share-events",
        json={
            "product_id": owned_product["id"],
            "share_id": owned_product["shares"][0]["id"],
            "event_type": "subscription",
            "evidence_stage": "confirmation",
            "confirmation_date": "2026-09-15",
            "units_delta": "120000.000000",
            "balance_after": "120000.000000",
            "business_ref": "MAIL-CONFIRM-001",
            "source_mail_item_id": mail_item_id,
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["status"] == "confirmed"
    assert created.json()["confirmed_at"]

    investor_ledger = client.get(
        f"/api/investors/{investor['id']}/share-events"
    ).json()
    assert investor_ledger["positions"][0]["current_units"] == "120000.000000"
    assert investor_ledger["positions"][0]["current_source"] == "event_balance"

    product_ledger = client.get(
        f"/api/products/{owned_product['id']}/investor-shares"
    )
    assert product_ledger.status_code == 200, product_ledger.text
    product_rows = product_ledger.json()["investors"]
    assert product_rows[0]["investor"]["id"] == investor["id"]
    assert product_rows[0]["ledger"]["positions"][0]["current_units"] == "120000.000000"

    with app.state.factory() as db:
        action = db.scalar(
            select(MailAction).where(MailAction.mail_item_id == mail_item_id)
        )
        assert action.status == "completed"
        assert action.result["object_type"] == "share_event"
        assert not db.scalar(
            select(ExceptionTask).where(
                ExceptionTask.manager_id == ids["a"],
                ExceptionTask.kind == "investor_share",
                ExceptionTask.status != "resolved",
            )
        )

    mismatch = client.post(
        f"/api/investors/{investor['id']}/position-snapshots",
        json={
            "product_id": owned_product["id"],
            "share_id": owned_product["shares"][0]["id"],
            "as_of_date": "2026-09-15",
            "units": "119000.000000",
            "source_mail_item_id": mail_item_id,
        },
    )
    assert mismatch.status_code == 201, mismatch.text
    tasks = client.get(f"/api/managers/{ids['a']}/tasks").json()
    difference = next(
        item
        for item in tasks
        if item["kind"] == "investor_share" and item["status"] != "resolved"
    )
    assert difference["payload"]["reason"] == "position_difference"
    assert difference["mail_item_id"] == mail_item_id
    assert difference["investor_position_snapshot"]["units"] == "119000.000000"

    login(client, "fund")
    assert all(
        item["kind"] != "investor_share"
        for item in client.get(f"/api/managers/{ids['a']}/tasks").json()
    )


def test_custodian_position_statement_auto_imports_and_is_idempotent(env):
    app, client, ids = env
    login(client)
    owned_product = product(client, ids["a"], "CUST01", shares=["总"])
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "日间净值列表"
    sheet.append(
        [
            "产品代码",
            "产品名称",
            "投资者名称",
            "份额日期",
            "持有份额",
            "份额最后变动日期",
            "占同级别份额比例",
            "产品总份额",
        ]
    )
    sheet.append(
        [
            owned_product["code"],
            owned_product["name"],
            "托管表新增投资者",
            "2026-09-15",
            "123456.780000",
            "2026-09-10",
            "10%",
            "1234567.8",
        ]
    )
    content = BytesIO()
    workbook.save(content)

    with app.state.factory.begin() as db:
        original = archive(
            db,
            app.state.settings,
            ids["a"],
            "investor-position.eml",
            b"From: custodian@example.invalid\nSubject: investor positions\n\nbody",
            "email",
        )
        mail_item = MailItem(
            manager_id=ids["a"],
            document_id=original.id,
            category="investor_redemption",
            title="投资人份额日报",
            sender="custodian@example.invalid",
            handling_mode="receipt",
            priority="normal",
            classification_source="rule",
            confidence=95,
            status="received",
        )
        db.add(mail_item)
        db.flush()
        attachment = archive(
            db,
            app.state.settings,
            ids["a"],
            "投资人份额.xlsx",
            content.getvalue(),
            "email_attachment",
            parent_id=original.id,
        )
        attachment_id = attachment.id
        mail_item_id = mail_item.id

    with app.state.factory.begin() as db:
        assert import_investor_position_documents(db, app.state.settings) == 1
    with app.state.factory.begin() as db:
        assert import_investor_position_documents(db, app.state.settings) == 0

    with app.state.factory() as db:
        investor = db.scalar(
            select(Investor).where(Investor.display_name == "托管表新增投资者")
        )
        assert investor.status == "pending"
        assert investor.source == "material"
        snapshot = db.scalar(
            select(InvestorPositionSnapshot).where(
                InvestorPositionSnapshot.investor_id == investor.id
            )
        )
        assert str(snapshot.units) == "123456.780000"
        assert snapshot.source_mail_item_id == mail_item_id
        assert snapshot.source_document_id == attachment_id
        material = db.get(DocumentMaterial, attachment_id)
        assert material.material_type == "position_statement"
        assert material.sensitivity == "investor_sensitive"
        assert material.organization_source == "automatic"
        assert db.scalar(
            select(DocumentMaterialInvestor).where(
                DocumentMaterialInvestor.document_id == attachment_id
            )
        ) is None
        assert db.scalar(
            select(DocumentMaterialProduct).where(
                DocumentMaterialProduct.document_id == attachment_id
            )
        ) is None

    materials = client.get(
        f"/api/managers/{ids['a']}/documents",
        params={"paginated": "true"},
    ).json()
    assert attachment_id not in {item["id"] for item in materials["items"]}

    investors = client.get(f"/api/managers/{ids['a']}/investors").json()
    imported = next(item for item in investors if item["id"] == investor.id)
    assert imported["product_ids"] == [owned_product["id"]]
    workspace = client.get(
        f"/api/managers/{ids['a']}/material-workspace"
    ).json()
    relation = next(
        item
        for item in workspace["relations"]
        if item["investor_id"] == investor.id
        and item["product_id"] == owned_product["id"]
    )
    assert relation["holding_status"] == "active"
    assert relation["relation_source"] == "position"
    assert relation["current_units"] == "123456.780000"
    assert relation["as_of_date"] == "2026-09-15"
    ledger = client.get(f"/api/investors/{investor.id}/share-events").json()
    assert ledger["positions"][0]["current_units"] == "123456.780000"
    assert ledger["positions"][0]["current_source"] == "snapshot"
