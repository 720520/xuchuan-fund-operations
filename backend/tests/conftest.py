import os
from urllib.parse import urlencode
from uuid import uuid4

import pytest
from app.config import Settings
from app.db import Base
from app.immutability import install_guards
from app.main import create_app
from app.models import Group, Manager, Membership, User
from app.security import password_hash
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

PASSWORD = "test-only-password-012345"
ORIGIN = "http://testserver"


@pytest.fixture
def env(tmp_path):
    url = os.getenv("TEST_DATABASE_URL")
    cleanup = None
    if url:
        if not url.endswith("/xuchuan_test"):
            raise ValueError("Tests require the dedicated xuchuan_test database")
        schema = "qa_" + uuid4().hex
        control = create_engine(url)
        with control.begin() as c:
            c.execute(text(f'CREATE SCHEMA "{schema}"'))
        cleanup = (control, schema)
        url += "?" + urlencode({"options": f"-csearch_path={schema}"})
    settings = Settings(
        database_url=url or f"sqlite:///{tmp_path}/test.db",
        storage=tmp_path / "archive",
        mail_key_file=tmp_path / "mail-encryption.key",
        cookie_secure=False,
        origins=(ORIGIN,),
    )
    app = create_app(settings)
    Base.metadata.create_all(app.state.engine)
    with app.state.engine.begin() as c:
        install_guards(c)
    ids = {}
    with app.state.factory.begin() as db:
        g = Group(name="测试集团")
        other = Group(name="另一集团")
        db.add_all([g, other])
        db.flush()
        for key, group in [("a", g), ("b", g), ("c", other)]:
            m = Manager(name=f"测试牌照{key}", group_id=group.id)
            db.add(m)
            db.flush()
            ids[key] = m.id
        encoded = password_hash(PASSWORD)
        for name, manager, roles, download in [
            ("ops", "a", ["operator", "admin"], True),
            ("colleague", "a", ["operator"], False),
            ("otherops", "b", ["operator"], True),
            ("admin", "a", ["admin"], False),
            ("fund", "a", ["fund_manager"], True),
            ("outsider", "c", ["operator"], True),
        ]:
            u = User(email=f"{name}@test.invalid", name=name, password_hash=encoded)
            db.add(u)
            db.flush()
            ids[name] = u.id
            db.add(
                Membership(
                    user_id=u.id,
                    manager_id=ids[manager],
                    roles=roles,
                    can_download=download,
                )
            )
    with TestClient(app, headers={"origin": ORIGIN}) as client:
        yield app, client, ids
    app.state.engine.dispose()
    if cleanup:
        control, schema = cleanup
        # This exact UUID-named schema was created above in xuchuan_test; never a shared schema.
        with control.begin() as c:
            c.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        control.dispose()


def login(client, name="ops"):
    result = client.post(
        "/api/auth/login", json={"email": f"{name}@test.invalid", "password": PASSWORD}
    )
    assert result.status_code == 200, result.text


def product(client, manager, code="F001", shares=None):
    result = client.post(
        f"/api/managers/{manager}/products",
        json={"code": code, "name": "测试产品" + code, "shares": shares or ["A"]},
    )
    assert result.status_code == 201, result.text
    return next(
        p
        for p in client.get(f"/api/managers/{manager}/products").json()
        if p["id"] == result.json()["id"]
    )


def nav_data(p, value="1.0500", day="2026-08-28", share=0):
    return {
        "product_id": p["id"],
        "share_id": p["shares"][share]["id"],
        "valuation_date": day,
        "unit_nav": value,
        "net_assets": "12345678.90",
    }
