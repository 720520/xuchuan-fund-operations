"""Durable trading-day receipt scheduling; existing managers explicitly enable it."""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("receipt_policies",
        sa.Column("manager_id", sa.String(36), sa.ForeignKey("managers.id"), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("start_date", sa.String(10), nullable=False),
        sa.Column("followup_time", sa.String(5), nullable=False),
        sa.Column("last_scheduled_date", sa.String(10)),
        sa.Column("last_checked_at", sa.String(40)),
        sa.Column("error", sa.String(250)),
    )
    op.create_table("receipt_expectations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("manager_id", sa.String(36), nullable=False),
        sa.Column("product_id", sa.String(36), nullable=False),
        sa.Column("share_id", sa.String(36), nullable=False),
        sa.Column("valuation_date", sa.String(10), nullable=False),
        sa.Column("due_date", sa.String(10), nullable=False),
        sa.Column("cutoff", sa.String(5), nullable=False),
        sa.Column("followup_date", sa.String(10)),
        sa.Column("followup_time", sa.String(5), nullable=False),
        sa.Column("calendar_version", sa.String(40), nullable=False),
        sa.Column("received_at", sa.String(40)),
        sa.Column("document_id", sa.String(36)),
        sa.Column("record_id", sa.String(36)),
        sa.Column("cancelled", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["share_id", "manager_id", "product_id"], ["share_classes.id", "share_classes.manager_id", "share_classes.product_id"]),
        sa.ForeignKeyConstraint(["document_id", "manager_id"], ["documents.id", "documents.manager_id"]),
        sa.ForeignKeyConstraint(["record_id", "manager_id", "share_id", "valuation_date"], ["nav_records.id", "nav_records.manager_id", "nav_records.share_id", "nav_records.valuation_date"]),
        sa.UniqueConstraint("share_id", "valuation_date"),
    )
    op.create_index("ix_receipt_pending", "receipt_expectations", ["manager_id", "cancelled", "received_at"])


def downgrade():
    raise RuntimeError("应收和补发留痕不能通过回滚删除；请使用验证过的备份")
