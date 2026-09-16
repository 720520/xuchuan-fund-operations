import os
from pathlib import Path
from urllib.parse import urlencode
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


def test_initial_migration_and_append_only_guards(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path}/migration.db"
    monkeypatch.setenv("DATABASE_URL", url)
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(config, "head")
    command.upgrade(config, "head")  # no duplicate triggers on repeat upgrade
    command.check(config)
    engine = create_engine(url)
    tables = inspect(engine).get_table_names()
    assert {
        "effective_nav",
        "nav_records",
        "audit_events",
        "documents",
        "parse_jobs",
        "validation_rules",
        "product_filings",
        "mail_items",
        "mail_item_products",
        "mail_actions",
        "document_materials",
        "document_material_products",
        "document_material_investors",
        "investors",
        "investor_products",
        "investor_bank_accounts",
        "investor_bank_account_products",
        "investor_share_events",
        "investor_position_snapshots",
    } <= set(tables)
    with engine.connect() as c:
        triggers = (
            c.execute(text("SELECT name FROM sqlite_master WHERE type='trigger'"))
            .scalars()
            .all()
        )
        assert len(triggers) == 6
    assert {
        "host",
        "port",
        "tls",
        "username",
        "credential_ciphertext",
        "all_folders",
        "send_id",
    } <= {column["name"] for column in inspect(engine).get_columns("mailboxes")}
    assert "folder" in {
        column["name"] for column in inspect(engine).get_columns("mail_receipts")
    }
    assert any(
        set(constraint["column_names"])
        == {"mailbox_id", "folder", "uid_validity", "message_uid"}
        for constraint in inspect(engine).get_unique_constraints("mail_receipts")
    )
    assert {
        "lifecycle_status",
        "lifecycle_date",
        "lifecycle_reason",
        "lifecycle_updated_at",
        "lifecycle_updated_by",
    } <= {column["name"] for column in inspect(engine).get_columns("products")}
    material_columns = inspect(engine).get_columns("document_materials")
    assert {"sensitivity", "material_type", "organization_source"} <= {
        column["name"]
        for column in material_columns
    }
    assert next(
        column for column in material_columns if column["name"] == "confirmed_by"
    )["nullable"]
    assert {
        "suitability_class",
        "certificate_number_ciphertext",
        "certificate_number_masked",
        "risk_level",
        "qualified_material_status",
        "profile_source_document_id",
    } <= {column["name"] for column in inspect(engine).get_columns("investors")}
    engine.dispose()


def test_postgresql_migration_reaches_material_organization(monkeypatch):
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("requires the dedicated PostgreSQL test database")
    if not url.endswith("/xuchuan_test"):
        raise ValueError("Tests require the dedicated xuchuan_test database")
    schema = "migration_" + uuid4().hex
    control = create_engine(url)
    try:
        with control.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        scoped_url = url + "?" + urlencode({"options": f"-csearch_path={schema}"})
        monkeypatch.setenv("DATABASE_URL", scoped_url)
        config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
        command.upgrade(config, "head")
        command.check(config)
        engine = create_engine(scoped_url)
        try:
            tables = set(inspect(engine).get_table_names())
            assert {
                "document_materials",
                "document_material_products",
                "document_material_investors",
                "investors",
                "investor_products",
                "investor_bank_accounts",
                "investor_bank_account_products",
                "investor_share_events",
                "investor_position_snapshots",
            } <= tables
        finally:
            engine.dispose()
    finally:
        with control.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        control.dispose()
