"""Classify archived mail before routing attachments to business workflows."""

from alembic import op
import sqlalchemy as sa


revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "mail_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("manager_id", sa.String(36), nullable=False),
        sa.Column("document_id", sa.String(36), nullable=False, unique=True),
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("sender", sa.String(500), nullable=False),
        sa.Column("business_date", sa.String(10)),
        sa.Column("handling_mode", sa.String(20), nullable=False),
        sa.Column("priority", sa.String(20), nullable=False),
        sa.Column("classification_source", sa.String(20), nullable=False),
        sa.Column("confidence", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("excerpt", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id", "manager_id"], ["documents.id", "documents.manager_id"]
        ),
        sa.UniqueConstraint("id", "manager_id"),
    )
    op.create_index("ix_mail_items_manager_id", "mail_items", ["manager_id"])
    op.create_table(
        "mail_item_products",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("manager_id", sa.String(36), nullable=False),
        sa.Column("mail_item_id", sa.String(36), nullable=False),
        sa.Column("product_id", sa.String(36), nullable=False),
        sa.ForeignKeyConstraint(
            ["mail_item_id", "manager_id"], ["mail_items.id", "mail_items.manager_id"]
        ),
        sa.ForeignKeyConstraint(
            ["product_id", "manager_id"], ["products.id", "products.manager_id"]
        ),
        sa.UniqueConstraint("mail_item_id", "product_id"),
    )
    op.create_table(
        "mail_actions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("manager_id", sa.String(36), nullable=False),
        sa.Column("mail_item_id", sa.String(36), nullable=False, unique=True),
        sa.Column("suggested_action", sa.String(500), nullable=False),
        sa.Column("due_at", sa.String(40)),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("assignee_id", sa.String(36), sa.ForeignKey("users.id")),
        sa.Column("result", sa.JSON()),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["mail_item_id", "manager_id"], ["mail_items.id", "mail_items.manager_id"]
        ),
    )
    op.create_index("ix_mail_actions_manager_id", "mail_actions", ["manager_id"])


def downgrade():
    raise RuntimeError("邮件分类、待办与原件关联不可通过回滚删除；请使用验证过的备份")
