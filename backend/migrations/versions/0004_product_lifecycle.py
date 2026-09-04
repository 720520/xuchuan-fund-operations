"""Product lifecycle status and liquidation traceability."""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "products",
        sa.Column(
            "lifecycle_status",
            sa.String(20),
            nullable=False,
            server_default="active",
        ),
    )
    op.add_column("products", sa.Column("lifecycle_date", sa.String(10), nullable=True))
    op.add_column("products", sa.Column("lifecycle_reason", sa.Text(), nullable=True))
    op.add_column(
        "products", sa.Column("lifecycle_updated_at", sa.String(40), nullable=True)
    )
    op.add_column(
        "products",
        sa.Column("lifecycle_updated_by", sa.String(36), nullable=True),
    )


def downgrade():
    raise RuntimeError("业务留痕迁移不可回滚；请从经过验证的备份恢复")
