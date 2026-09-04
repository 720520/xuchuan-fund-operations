from datetime import date

import pytest
from app.config import Settings
from app.db import Base
from app.immutability import install_guards
from app.models import (
    AuditEvent,
    Document,
    ExceptionTask,
    Group,
    Manager,
    Product,
    ShareClass,
    User,
)
from app.services import change_product_lifecycle, refresh_missing
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker


@pytest.fixture
def lifecycle_db(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path}/lifecycle.db",
        storage=tmp_path / "archive",
        mail_key_file=tmp_path / "mail.key",
        cookie_secure=False,
    )
    engine = create_engine(settings.database_url)
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        install_guards(connection)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory.begin() as db:
        group = Group(name="测试集团")
        user = User(email="admin@test.invalid", name="admin", password_hash="unused")
        db.add_all([group, user])
        db.flush()
        manager = Manager(name="测试牌照", group_id=group.id)
        db.add(manager)
        db.flush()
        product = Product(manager_id=manager.id, code="LIFE001", name="生命周期测试产品")
        db.add(product)
        db.flush()
        share = ShareClass(manager_id=manager.id, product_id=product.id, name="总")
        db.add(share)
        db.flush()
        issue = ExceptionTask(
            manager_id=manager.id,
            product_id=product.id,
            share_id=share.id,
            valuation_date="2026-08-31",
            kind="missing",
            dedup_key=f"missing:{share.id}:2026-08-31",
            payload={},
        )
        db.add(issue)
        db.flush()
        ids = product.id, user.id, issue.id, manager.id
    yield settings, factory, ids
    engine.dispose()


def test_liquidation_requires_material_and_preserves_evidence(lifecycle_db):
    settings, factory, (product_id, user_id, issue_id, _) = lifecycle_db
    with factory.begin() as db:
        product = db.get(Product, product_id)
        actor = db.get(User, user_id)
        with pytest.raises(HTTPException, match="清算报告"):
            change_product_lifecycle(
                db,
                settings,
                product,
                actor,
                "liquidated",
                date(2026, 8, 31),
                "清算完成",
            )
        material = change_product_lifecycle(
            db,
            settings,
            product,
            actor,
            "liquidated",
            date(2026, 8, 31),
            "托管确认清算完成",
            "清算报告.pdf",
            b"verified material",
        )
        assert product.lifecycle_status == "liquidated"
        assert product.expected is False
        assert product.frequency == "off"
        assert material.product_id == product.id
        assert material.source == "lifecycle_material"
        assert db.get(ExceptionTask, issue_id).status == "resolved"
        assert db.scalar(
            select(AuditEvent).where(
                AuditEvent.object_id == product.id,
                AuditEvent.action == "product.lifecycle_changed",
            )
        )
        assert db.scalar(select(Document).where(Document.id == material.id))


def test_restoring_product_does_not_reenable_receipts(lifecycle_db):
    settings, factory, (product_id, user_id, _, manager_id) = lifecycle_db
    with factory.begin() as db:
        product = db.get(Product, product_id)
        actor = db.get(User, user_id)
        change_product_lifecycle(
            db,
            settings,
            product,
            actor,
            "liquidated",
            date(2026, 8, 31),
            "清算完成",
            "托管确认.pdf",
            b"verified material",
        )
        change_product_lifecycle(
            db,
            settings,
            product,
            actor,
            "active",
            date(2026, 9, 1),
            "清算状态录入有误，恢复运作",
        )
        assert product.lifecycle_status == "active"
        assert product.expected is False
        assert product.frequency == "off"
        refresh_missing(db, manager_id, on_date=date(2026, 9, 1))
        open_missing = list(
            db.scalars(
                select(ExceptionTask).where(
                    ExceptionTask.product_id == product.id,
                    ExceptionTask.kind == "missing",
                    ExceptionTask.status != "resolved",
                )
            )
        )
        assert open_missing == []
