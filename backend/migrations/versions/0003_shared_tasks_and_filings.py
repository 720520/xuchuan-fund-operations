"""Shared exception handling and minimal product-filing records."""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "product_filings",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("manager_id", sa.String(36), nullable=False),
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("strategy", sa.String(80), nullable=False),
        sa.Column("shares", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_by", sa.String(36), nullable=False),
        sa.Column("product_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("completed_at", sa.String(40), nullable=True),
        sa.ForeignKeyConstraint(["manager_id"], ["managers.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_product_filings_manager_id", "product_filings", ["manager_id"])
    # Legacy claimed tasks return to the shared queue. Evidence and revisions remain.
    op.execute(
        "UPDATE exception_tasks SET status = 'open', assignee_id = NULL, "
        "revision = revision + 1 WHERE status = 'processing'"
    )


def downgrade():
    raise RuntimeError("业务留痕迁移不可回滚；请从经过验证的备份恢复")
