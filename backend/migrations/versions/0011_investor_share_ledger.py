"""Add append-only investor share events and custodian position snapshots."""

from alembic import op
import sqlalchemy as sa


revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "investor_share_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("manager_id", sa.String(36), nullable=False),
        sa.Column("investor_id", sa.String(36), nullable=False),
        sa.Column("product_id", sa.String(36), nullable=False),
        sa.Column("share_id", sa.String(36), nullable=True),
        sa.Column("event_type", sa.String(30), nullable=False),
        sa.Column("evidence_stage", sa.String(20), nullable=False, server_default="notice"),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("application_date", sa.String(10), nullable=True),
        sa.Column("confirmation_date", sa.String(10), nullable=True),
        sa.Column("effective_date", sa.String(10), nullable=True),
        sa.Column("requested_amount", sa.Numeric(24, 6), nullable=True),
        sa.Column("confirmed_amount", sa.Numeric(24, 6), nullable=True),
        sa.Column("units_delta", sa.Numeric(24, 6), nullable=True),
        sa.Column("unit_nav", sa.Numeric(18, 8), nullable=True),
        sa.Column("fee_amount", sa.Numeric(24, 6), nullable=True),
        sa.Column("balance_after", sa.Numeric(24, 6), nullable=True),
        sa.Column("business_ref", sa.String(150), nullable=True),
        sa.Column("source_mail_item_id", sa.String(36), nullable=True),
        sa.Column("source_document_id", sa.String(36), nullable=True),
        sa.Column("supersedes_event_id", sa.String(36), nullable=True),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("confirmed_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
        sa.Column("confirmed_at", sa.String(40), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(["investor_id", "manager_id"], ["investors.id", "investors.manager_id"]),
        sa.ForeignKeyConstraint(["product_id", "manager_id"], ["products.id", "products.manager_id"]),
        sa.ForeignKeyConstraint(["share_id", "manager_id", "product_id"], ["share_classes.id", "share_classes.manager_id", "share_classes.product_id"]),
        sa.ForeignKeyConstraint(["source_mail_item_id", "manager_id"], ["mail_items.id", "mail_items.manager_id"]),
        sa.ForeignKeyConstraint(["source_document_id", "manager_id"], ["documents.id", "documents.manager_id"]),
        sa.ForeignKeyConstraint(["supersedes_event_id", "manager_id"], ["investor_share_events.id", "investor_share_events.manager_id"]),
        sa.UniqueConstraint("id", "manager_id"),
    )
    op.create_index("ix_investor_share_events_manager_id", "investor_share_events", ["manager_id"])
    op.create_index("ix_investor_share_events_investor_id", "investor_share_events", ["investor_id"])
    op.create_index("ix_investor_share_events_product_id", "investor_share_events", ["product_id"])
    op.create_index("ix_investor_share_events_status", "investor_share_events", ["status"])
    op.create_index("ix_investor_share_event_timeline", "investor_share_events", ["manager_id", "investor_id", "product_id", "effective_date"])

    op.create_table(
        "investor_position_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("manager_id", sa.String(36), nullable=False),
        sa.Column("investor_id", sa.String(36), nullable=False),
        sa.Column("product_id", sa.String(36), nullable=False),
        sa.Column("share_id", sa.String(36), nullable=True),
        sa.Column("as_of_date", sa.String(10), nullable=False),
        sa.Column("units", sa.Numeric(24, 6), nullable=False),
        sa.Column("source_mail_item_id", sa.String(36), nullable=True),
        sa.Column("source_document_id", sa.String(36), nullable=True),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.ForeignKeyConstraint(["investor_id", "manager_id"], ["investors.id", "investors.manager_id"]),
        sa.ForeignKeyConstraint(["product_id", "manager_id"], ["products.id", "products.manager_id"]),
        sa.ForeignKeyConstraint(["share_id", "manager_id", "product_id"], ["share_classes.id", "share_classes.manager_id", "share_classes.product_id"]),
        sa.ForeignKeyConstraint(["source_mail_item_id", "manager_id"], ["mail_items.id", "mail_items.manager_id"]),
        sa.ForeignKeyConstraint(["source_document_id", "manager_id"], ["documents.id", "documents.manager_id"]),
        sa.UniqueConstraint("id", "manager_id"),
        sa.UniqueConstraint("investor_id", "product_id", "share_id", "as_of_date", "source_document_id", name="uq_investor_position_snapshot_source"),
    )
    op.create_index("ix_investor_position_snapshots_manager_id", "investor_position_snapshots", ["manager_id"])
    op.create_index("ix_investor_position_snapshots_investor_id", "investor_position_snapshots", ["investor_id"])
    op.create_index("ix_investor_position_snapshots_product_id", "investor_position_snapshots", ["product_id"])


def downgrade():
    raise RuntimeError("投资者份额流水和持仓快照属于业务留痕，不允许通过回滚删除")
