from app.mailbox_security import decrypt_sensitive_value
from app.models import (
    AuditEvent,
    Investor,
    InvestorBankAccount,
    InvestorBankAccountProduct,
    Membership,
    User,
)
from app.security import password_hash
from conftest import PASSWORD, login, product
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
