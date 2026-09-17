from sqlalchemy import select

from app.models import (
    AuditEvent,
    Document,
    DocumentMaterial,
    DocumentMaterialProduct,
    ParseJob,
)
from conftest import login, product


def upload_material(
    client,
    manager,
    product_id="",
    filename="托管协议.pdf",
    content=b"archived-original",
):
    response = client.post(
        f"/api/managers/{manager}/documents",
        data={"product_id": product_id},
        files={"file": (filename, content, "application/pdf")},
    )
    assert response.status_code == 201, response.text
    return response.json()


def organization(revision, product_ids, **changes):
    return {
        "revision": revision,
        "category": "contract",
        "material_type": "contract",
        "title": "托管协议（已核对）",
        "business_date": "2026-09-08",
        "period_start": None,
        "period_end": None,
        "product_ids": product_ids,
        "notes": "已核对签署页",
        "confirmed": True,
        **changes,
    }


def test_product_directory_upload_is_linked_without_nav_parsing(env):
    app, client, ids = env
    login(client)
    linked_product = product(client, ids["a"], "MATDIR")

    response = client.post(
        f"/api/managers/{ids['a']}/documents",
        data={
            "product_id": linked_product["id"],
            "material_scope": "product",
        },
        files={"file": ("产品合同.pdf", b"product-directory-original", "application/pdf")},
    )
    assert response.status_code == 201, response.text
    document_id = response.json()["id"]

    listed = client.get(f"/api/managers/{ids['a']}/documents").json()
    staged = next(item for item in listed if item["id"] == document_id)
    assert staged["material_status"] == "pending"
    assert staged["sensitivity"] == "standard"
    assert staged["product_ids"] == [linked_product["id"]]
    assert staged["job"]["status"] == "skipped"
    assert "产品资料已安全归档" in staged["job"]["result"]["skip_reason"]

    with app.state.factory() as db:
        event = db.scalar(
            select(AuditEvent).where(
                AuditEvent.object_id == document_id,
                AuditEvent.action == "document.product_linked",
            )
        )
        assert event.details["material_scope"] == "product"


def test_material_organization_preserves_original_and_supports_multiple_products(env):
    app, client, ids = env
    login(client)
    first = product(client, ids["a"], "MAT001")
    second = product(client, ids["a"], "MAT002")
    uploaded = upload_material(client, ids["a"], first["id"])

    before = client.get(f"/api/managers/{ids['a']}/documents").json()[0]
    assert before["material_status"] == "pending"
    assert before["material_revision"] == 0
    assert before["product_ids"] == [first["id"]]
    with app.state.factory.begin() as db:
        job = db.scalar(select(ParseJob).where(ParseJob.document_id == uploaded["id"]))
        job.status = "review"
        job.result = {"errors": [{"reason": "尚无解析器"}]}

    saved = client.put(
        f"/api/documents/{uploaded['id']}/material",
        json=organization(0, [first["id"], second["id"]]),
    )
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["category"] == "contract"
    assert body["material_type"] == "contract"
    assert body["material_status"] == "organized"
    assert body["material_revision"] == 1
    assert set(body["product_ids"]) == {first["id"], second["id"]}
    assert body["job"]["status"] == "skipped"
    assert "非净值" in body["job"]["result"]["skip_reason"]
    assert client.post(f"/api/documents/{uploaded['id']}/reparse").status_code == 422

    stale = client.put(
        f"/api/documents/{uploaded['id']}/material",
        json=organization(0, [second["id"]]),
    )
    assert stale.status_code == 409

    changed = client.put(
        f"/api/documents/{uploaded['id']}/material",
        json=organization(
            1,
            [second["id"]],
            category="periodic_report",
            material_type="custom",
            business_date=None,
            period_start="2026-07-01",
            period_end="2026-09-30",
        ),
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["material_revision"] == 2
    assert changed.json()["product_ids"] == [second["id"]]

    listed = client.get(f"/api/managers/{ids['a']}/documents").json()[0]
    assert listed["category"] == "periodic_report"
    assert listed["material_type"] == "custom"
    assert listed["period_start"] == "2026-07-01"
    assert listed["period_end"] == "2026-09-30"
    assert listed["products"] == [{"id": second["id"], "name": second["name"]}]

    with app.state.factory() as db:
        original = db.get(Document, uploaded["id"])
        assert original.filename == "托管协议.pdf"
        assert original.product_id == first["id"]
        assert original.sha256 == uploaded["sha256"]
        material = db.get(DocumentMaterial, uploaded["id"])
        assert material.revision == 2
        assert material.material_type == "custom"
        assert list(
            db.scalars(
                select(DocumentMaterialProduct.product_id).where(
                    DocumentMaterialProduct.document_id == uploaded["id"]
                )
            )
        ) == [second["id"]]
        events = list(
            db.scalars(
                select(AuditEvent).where(
                    AuditEvent.object_id == uploaded["id"],
                    AuditEvent.action == "document.material_organized",
                )
            )
        )
        assert len(events) == 2
        assert events[-1].details["before"]["revision"] == 1
        assert events[-1].details["after"]["revision"] == 2


def test_material_organization_routes_nav_and_rejects_invalid_scope(env):
    app, client, ids = env
    login(client)
    own = product(client, ids["a"], "MAT003")
    uploaded = upload_material(client, ids["a"])

    nav = client.put(
        f"/api/documents/{uploaded['id']}/material",
        json=organization(
            0,
            [own["id"]],
            category="nav_valuation",
            title="每日净值",
        ),
    )
    assert nav.status_code == 200, nav.text
    assert nav.json()["job"]["status"] == "queued"

    invalid_period = client.put(
        f"/api/documents/{uploaded['id']}/material",
        json=organization(
            1,
            [own["id"]],
            period_start="2026-09-30",
            period_end="2026-09-01",
        ),
    )
    assert invalid_period.status_code == 422

    login(client, "otherops")
    other = product(client, ids["b"], "MAT004")
    login(client)
    cross_scope = client.put(
        f"/api/documents/{uploaded['id']}/material",
        json=organization(1, [other["id"]]),
    )
    assert cross_scope.status_code == 422

    login(client, "fund")
    denied = client.put(
        f"/api/documents/{uploaded['id']}/material",
        json=organization(1, [own["id"]]),
    )
    assert denied.status_code == 403


def test_material_server_pagination_search_and_subject_filters(env):
    app, client, ids = env
    login(client)
    first = product(client, ids["a"], "PAGE001")
    second = product(client, ids["a"], "PAGE002")
    investor = client.post(
        f"/api/managers/{ids['a']}/investors",
        json={
            "revision": 0,
            "investor_type": "institution",
            "display_name": "分页检索机构",
            "status": "confirmed",
            "source": "manual",
            "product_ids": [first["id"]],
            "notes": "",
        },
    ).json()
    contract = upload_material(
        client,
        ids["a"],
        first["id"],
        "分页合同甲.pdf",
        b"page-contract",
    )
    pending = upload_material(
        client, ids["a"], filename="未整理乙.pdf", content=b"page-pending"
    )
    report = upload_material(
        client, ids["a"], filename="季度报告丙.pdf", content=b"page-report"
    )
    contract_result = client.put(
        f"/api/documents/{contract['id']}/material",
        json=organization(
            0,
            [first["id"]],
            investor_ids=[investor["id"]],
            sensitivity="investor_sensitive",
        ),
    )
    assert contract_result.status_code == 200, contract_result.text
    report_result = client.put(
        f"/api/documents/{report['id']}/material",
        json=organization(
            0,
            [second["id"]],
            category="periodic_report",
            title="第三季度运行报告",
        ),
    )
    assert report_result.status_code == 200, report_result.text

    page = client.get(
        f"/api/managers/{ids['a']}/documents",
        params={"paginated": "true", "limit": 2, "offset": 0},
    )
    assert page.status_code == 200, page.text
    body = page.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2
    assert body["counts"] == {
        "all": 3,
        "pending": 1,
        "linked": 2,
        "attention": 1,
        "work": 1,
    }
    second_page = client.get(
        f"/api/managers/{ids['a']}/documents",
        params={"paginated": "true", "limit": 2, "offset": 2},
    ).json()
    assert second_page["total"] == 3
    assert len(second_page["items"]) == 1

    by_investor = client.get(
        f"/api/managers/{ids['a']}/documents",
        params={"paginated": "true", "investor_id": investor["id"]},
    ).json()
    assert [item["id"] for item in by_investor["items"]] == [contract["id"]]
    assert by_investor["items"][0]["sensitivity"] == "investor_sensitive"

    by_search = client.get(
        f"/api/managers/{ids['a']}/documents",
        params={"paginated": "true", "q": "分页检索机构"},
    ).json()
    assert [item["id"] for item in by_search["items"]] == [contract["id"]]
    by_category = client.get(
        f"/api/managers/{ids['a']}/documents",
        params={"paginated": "true", "category": "periodic_report"},
    ).json()
    assert [item["id"] for item in by_category["items"]] == [report["id"]]
    by_pending = client.get(
        f"/api/managers/{ids['a']}/documents",
        params={"paginated": "true", "status": "pending"},
    ).json()
    assert [item["id"] for item in by_pending["items"]] == [pending["id"]]

    # A formal document may mention an investor and a different product, but
    # document co-occurrence must never create a business relationship.
    cross_material = client.put(
        f"/api/documents/{report['id']}/material",
        json=organization(
            1,
            [second["id"]],
            investor_ids=[investor["id"]],
            sensitivity="investor_sensitive",
            category="periodic_report",
            title="第三季度运行报告",
        ),
    )
    assert cross_material.status_code == 200, cross_material.text

    # The subject workspace must aggregate the complete archive instead of the
    # legacy, non-paginated 300-row response used by older screens.
    with app.state.factory.begin() as db:
        for index in range(301):
            document_id = f"bulk-material-{index:03}"
            db.add(
                Document(
                    id=document_id,
                    manager_id=ids["a"],
                    product_id=first["id"],
                    filename=f"历史材料-{index:03}.pdf",
                    sha256=f"{index:064x}",
                    storage_key=f"qa/{document_id}",
                    size=1,
                    media_type="application/pdf",
                    source="upload",
                )
            )
            db.add(
                DocumentMaterial(
                    document_id=document_id,
                    manager_id=ids["a"],
                    category="contract",
                    title=f"历史材料 {index:03}",
                    status="organized",
                )
            )
            db.add(
                DocumentMaterialProduct(
                    manager_id=ids["a"],
                    document_id=document_id,
                    product_id=first["id"],
                )
            )

    workspace = client.get(
        f"/api/managers/{ids['a']}/material-workspace"
    )
    assert workspace.status_code == 200, workspace.text
    workspace_body = workspace.json()
    first_stats = next(
        item for item in workspace_body["products"] if item["id"] == first["id"]
    )
    assert first_stats == {
        "id": first["id"],
        "material_count": 302,
        "attention_count": 0,
        "relation_count": 1,
    }
    investor_stats = next(
        item
        for item in workspace_body["investors"]
        if item["id"] == investor["id"]
    )
    assert investor_stats["material_count"] == 2
    assert investor_stats["relation_count"] == 1
    assert workspace_body["relations"] == [
        {
            "product_id": first["id"],
            "investor_id": investor["id"],
            "material_count": 1,
            "attention_count": 0,
            "holding_status": "confirmed",
            "relation_source": "administrator",
            "current_units": None,
            "as_of_date": None,
        }
    ]

    assert isinstance(client.get(f"/api/managers/{ids['a']}/documents").json(), list)
