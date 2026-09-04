"""Frozen v0.1 initial schema. Future changes require a new migration."""

from alembic import op
import sqlalchemy as sa
from app.immutability import install_guards

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "groups",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "login_attempts",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("failures", sa.Integer(), nullable=False),
        sa.Column("blocked_until", sa.String(length=40), nullable=True),
        sa.PrimaryKeyConstraint("key"),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_table(
        "managers",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("group_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.ForeignKeyConstraint(
            ["group_id"],
            ["groups.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("group_id", "name"),
    )
    op.create_index(
        op.f("ix_managers_group_id"), "managers", ["group_id"], unique=False
    )
    op.create_table(
        "sessions",
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("expires_at", sa.String(length=40), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("token_hash"),
    )
    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("manager_id", sa.String(length=36), nullable=False),
        sa.Column("actor_id", sa.String(length=36), nullable=True),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("object_id", sa.String(length=36), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["manager_id"],
            ["managers.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_audit_events_manager_id"), "audit_events", ["manager_id"], unique=False
    )
    op.create_table(
        "mailboxes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("manager_id", sa.String(length=36), nullable=False),
        sa.Column("label", sa.String(length=100), nullable=False),
        sa.Column("env_prefix", sa.String(length=80), nullable=False),
        sa.Column("since", sa.String(length=10), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("last_sync", sa.String(length=40), nullable=True),
        sa.Column("error", sa.String(length=200), nullable=True),
        sa.ForeignKeyConstraint(
            ["manager_id"],
            ["managers.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("env_prefix"),
    )
    op.create_table(
        "memberships",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("manager_id", sa.String(length=36), nullable=False),
        sa.Column("roles", sa.JSON(), nullable=False),
        sa.Column("can_download", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["manager_id"],
            ["managers.id"],
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "manager_id"),
    )
    op.create_table(
        "products",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("manager_id", sa.String(length=36), nullable=False),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("strategy", sa.String(length=80), nullable=False),
        sa.Column("expected", sa.Boolean(), nullable=False),
        sa.Column("frequency", sa.String(length=12), nullable=False),
        sa.Column("weekday", sa.Integer(), nullable=False),
        sa.Column("cutoff", sa.String(length=5), nullable=False),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.ForeignKeyConstraint(
            ["manager_id"],
            ["managers.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "manager_id"),
        sa.UniqueConstraint("manager_id", "code"),
    )
    op.create_index(
        op.f("ix_products_manager_id"), "products", ["manager_id"], unique=False
    )
    op.create_table(
        "validation_rules",
        sa.Column("manager_id", sa.String(length=36), nullable=False),
        sa.Column("max_nav_change", sa.Numeric(precision=10, scale=6), nullable=True),
        sa.Column("updated_at", sa.String(length=40), nullable=False),
        sa.ForeignKeyConstraint(
            ["manager_id"],
            ["managers.id"],
        ),
        sa.PrimaryKeyConstraint("manager_id"),
    )
    op.create_table(
        "documents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("manager_id", sa.String(length=36), nullable=False),
        sa.Column("product_id", sa.String(length=36), nullable=True),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("storage_key", sa.String(length=200), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("media_type", sa.String(length=100), nullable=False),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column("uploader_id", sa.String(length=36), nullable=True),
        sa.Column("parent_id", sa.String(length=36), nullable=True),
        sa.Column("received_at", sa.String(length=40), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["manager_id"],
            ["managers.id"],
        ),
        sa.ForeignKeyConstraint(
            ["parent_id", "manager_id"],
            ["documents.id", "documents.manager_id"],
        ),
        sa.ForeignKeyConstraint(
            ["product_id", "manager_id"],
            ["products.id", "products.manager_id"],
        ),
        sa.ForeignKeyConstraint(
            ["uploader_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "manager_id"),
    )
    op.create_index(
        op.f("ix_documents_manager_id"), "documents", ["manager_id"], unique=False
    )
    op.create_table(
        "product_grants",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("product_id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "product_id"),
    )
    op.create_table(
        "share_classes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("product_id", sa.String(length=36), nullable=False),
        sa.Column("manager_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.ForeignKeyConstraint(
            ["product_id", "manager_id"],
            ["products.id", "products.manager_id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "manager_id", "product_id"),
        sa.UniqueConstraint("product_id", "name"),
    )
    op.create_table(
        "exception_tasks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("manager_id", sa.String(length=36), nullable=False),
        sa.Column("product_id", sa.String(length=36), nullable=True),
        sa.Column("share_id", sa.String(length=36), nullable=True),
        sa.Column("valuation_date", sa.String(length=10), nullable=True),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("dedup_key", sa.String(length=250), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("assignee_id", sa.String(length=36), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("resolution", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.Column("updated_at", sa.String(length=40), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["assignee_id"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["manager_id"],
            ["managers.id"],
        ),
        sa.ForeignKeyConstraint(
            ["product_id", "manager_id"],
            ["products.id", "products.manager_id"],
        ),
        sa.ForeignKeyConstraint(
            ["share_id"],
            ["share_classes.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("manager_id", "dedup_key"),
    )
    op.create_index(
        op.f("ix_exception_tasks_manager_id"),
        "exception_tasks",
        ["manager_id"],
        unique=False,
    )
    op.create_table(
        "mail_receipts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("mailbox_id", sa.String(length=36), nullable=False),
        sa.Column("uid_validity", sa.String(length=40), nullable=False),
        sa.Column("message_uid", sa.String(length=40), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
        ),
        sa.ForeignKeyConstraint(
            ["mailbox_id"],
            ["mailboxes.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("mailbox_id", "uid_validity", "message_uid"),
    )
    op.create_table(
        "nav_records",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("manager_id", sa.String(length=36), nullable=False),
        sa.Column("product_id", sa.String(length=36), nullable=False),
        sa.Column("share_id", sa.String(length=36), nullable=False),
        sa.Column("valuation_date", sa.String(length=10), nullable=False),
        sa.Column("unit_nav", sa.Numeric(precision=24, scale=10), nullable=False),
        sa.Column("accumulated_nav", sa.Numeric(precision=24, scale=10), nullable=True),
        sa.Column("net_assets", sa.Numeric(precision=30, scale=4), nullable=True),
        sa.Column("total_shares", sa.Numeric(precision=30, scale=4), nullable=True),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=True),
        sa.Column("actor_id", sa.String(length=36), nullable=True),
        sa.Column("received_at", sa.String(length=40), nullable=False),
        sa.Column("row_key", sa.String(length=100), nullable=True),
        sa.Column("reported_metrics", sa.JSON(), nullable=False),
        sa.Column("validation", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["document_id", "manager_id"],
            ["documents.id", "documents.manager_id"],
        ),
        sa.ForeignKeyConstraint(
            ["share_id", "manager_id", "product_id"],
            [
                "share_classes.id",
                "share_classes.manager_id",
                "share_classes.product_id",
            ],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "row_key"),
        sa.UniqueConstraint("id", "manager_id", "share_id", "valuation_date"),
    )
    op.create_index(
        "ix_nav_lookup",
        "nav_records",
        ["manager_id", "share_id", "valuation_date"],
        unique=False,
    )
    op.create_index(
        op.f("ix_nav_records_manager_id"), "nav_records", ["manager_id"], unique=False
    )
    op.create_table(
        "parse_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("manager_id", sa.String(length=36), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.String(length=40), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id", "manager_id"],
            ["documents.id", "documents.manager_id"],
        ),
        sa.ForeignKeyConstraint(
            ["manager_id"],
            ["managers.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id"),
    )
    op.create_table(
        "effective_nav",
        sa.Column("manager_id", sa.String(length=36), nullable=False),
        sa.Column("share_id", sa.String(length=36), nullable=False),
        sa.Column("valuation_date", sa.String(length=10), nullable=False),
        sa.Column("record_id", sa.String(length=36), nullable=False),
        sa.Column("reversal", sa.Boolean(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["manager_id"],
            ["managers.id"],
        ),
        sa.ForeignKeyConstraint(
            ["record_id", "manager_id", "share_id", "valuation_date"],
            [
                "nav_records.id",
                "nav_records.manager_id",
                "nav_records.share_id",
                "nav_records.valuation_date",
            ],
        ),
        sa.ForeignKeyConstraint(
            ["share_id"],
            ["share_classes.id"],
        ),
        sa.PrimaryKeyConstraint("share_id", "valuation_date"),
    )
    install_guards(op.get_bind())


def downgrade():
    raise RuntimeError(
        "Evidence tables cannot be destructively downgraded; restore a tested backup into a separate environment."
    )
