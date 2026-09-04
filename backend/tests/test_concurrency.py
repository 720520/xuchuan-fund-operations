from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from app.models import EffectiveNav, ExceptionTask, NavRecord, Product, ShareClass, User
from app.services import add_nav
from conftest import ORIGIN, login, nav_data, product
from fastapi.testclient import TestClient
from sqlalchemy import select


def postgres_only(app):
    if app.state.engine.dialect.name != "postgresql":
        pytest.skip("requires PostgreSQL row locks")


def test_concurrent_shared_resolution_only_one_member_wins(env):
    app, client, ids = env
    postgres_only(app)
    login(client)
    p = product(client, ids["a"])
    client.post(f"/api/managers/{ids['a']}/nav", json=nav_data(p, "1.05"))
    record = client.post(
        f"/api/managers/{ids['a']}/nav", json=nav_data(p, "1.10")
    ).json()
    issue = client.get(f"/api/managers/{ids['a']}/tasks").json()[0]
    barrier = Barrier(2)

    def resolve_as(name):
        with TestClient(app, headers={"origin": ORIGIN}) as c:
            login(c, name)
            barrier.wait(timeout=10)
            return c.post(
                f"/api/tasks/{issue['id']}/resolve",
                json={
                    "record_id": record["id"],
                    "revision": issue["revision"],
                    "reason": "并发共享处理测试",
                },
            ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(resolve_as, ["ops", "colleague"]))
    assert sorted(results) == [200, 409]


def test_concurrent_nav_has_one_effective_and_one_conflict(env):
    app, client, ids = env
    postgres_only(app)
    login(client)
    p = product(client, ids["a"])
    barrier = Barrier(2)

    def receive(value):
        with app.state.factory.begin() as db:
            fund = db.get(Product, p["id"])
            share = db.get(ShareClass, p["shares"][0]["id"])
            actor = db.get(User, ids["ops"])
            barrier.wait(timeout=10)
            add_nav(db, ids["a"], fund, share, nav_data(p, value), actor)

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(receive, ["1.1", "1.2"]))
    with app.state.factory() as db:
        assert len(list(db.scalars(select(NavRecord)))) == 2
        assert len(list(db.scalars(select(EffectiveNav)))) == 1
        assert (
            len(
                list(
                    db.scalars(
                        select(ExceptionTask).where(ExceptionTask.kind == "conflict")
                    )
                )
            )
            == 1
        )
