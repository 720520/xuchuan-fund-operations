"""Store mutable material organization separately from immutable originals."""

from alembic import op
import sqlalchemy as sa


revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "document_materials",
        sa.Column("document_id", sa.String(36), primary_key=True),
        sa.Column("manager_id", sa.String(36), nullable=False),
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("title", sa.String(500)),
        sa.Column("business_date", sa.String(10)),
        sa.Column("period_start", sa.String(10)),
        sa.Column("period_end", sa.String(10)),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("confirmed_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("confirmed_at", sa.String(40), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id", "manager_id"], ["documents.id", "documents.manager_id"]
        ),
        sa.UniqueConstraint("document_id", "manager_id"),
    )
    op.create_index(
        "ix_document_materials_manager_id", "document_materials", ["manager_id"]
    )
    op.create_table(
        "document_material_products",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("manager_id", sa.String(36), nullable=False),
        sa.Column("document_id", sa.String(36), nullable=False),
        sa.Column("product_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id", "manager_id"],
            ["document_materials.document_id", "document_materials.manager_id"],
        ),
        sa.ForeignKeyConstraint(
            ["product_id", "manager_id"], ["products.id", "products.manager_id"]
        ),
        sa.UniqueConstraint("document_id", "product_id"),
    )


def downgrade():
    raise RuntimeError("资料整理记录和关联留痕不可通过回滚删除；请使用验证过的备份")
