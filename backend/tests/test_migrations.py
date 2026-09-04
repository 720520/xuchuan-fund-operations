from pathlib import Path

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
    engine.dispose()
