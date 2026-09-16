"""Allow system-organized material metadata after successful NAV parsing."""

from alembic import op
import sqlalchemy as sa


revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "document_materials",
        sa.Column(
            "organization_source",
            sa.String(30),
            nullable=False,
            server_default="manual",
        ),
    )
    with op.batch_alter_table("document_materials") as batch_op:
        batch_op.alter_column(
            "confirmed_by",
            existing_type=sa.String(36),
            nullable=True,
        )


def downgrade():
    raise RuntimeError("系统整理资料及其关联留痕不可通过回滚删除；请使用验证过的备份")
