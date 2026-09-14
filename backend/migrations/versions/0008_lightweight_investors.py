"""Add lightweight investor subjects and sensitive material relationships."""

from alembic import op
import sqlalchemy as sa


revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "document_materials",
        sa.Column(
            "sensitivity",
            sa.String(30),
            nullable=False,
            server_default="standard",
        ),
    )
    op.create_table(
        "investors",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("manager_id", sa.String(36), nullable=False),
        sa.Column("investor_type", sa.String(30), nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("source", sa.String(30), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(36), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["manager_id"], ["managers.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.UniqueConstraint("id", "manager_id"),
    )
    op.create_index("ix_investors_manager_id", "investors", ["manager_id"])
    op.create_table(
        "investor_products",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("manager_id", sa.String(36), nullable=False),
        sa.Column("investor_id", sa.String(36), nullable=False),
        sa.Column("product_id", sa.String(36), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_by", sa.String(36), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.ForeignKeyConstraint(
            ["investor_id", "manager_id"], ["investors.id", "investors.manager_id"]
        ),
        sa.ForeignKeyConstraint(
            ["product_id", "manager_id"], ["products.id", "products.manager_id"]
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.UniqueConstraint("investor_id", "product_id"),
    )
    op.create_table(
        "document_material_investors",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("manager_id", sa.String(36), nullable=False),
        sa.Column("document_id", sa.String(36), nullable=False),
        sa.Column("investor_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id", "manager_id"],
            ["document_materials.document_id", "document_materials.manager_id"],
        ),
        sa.ForeignKeyConstraint(
            ["investor_id", "manager_id"], ["investors.id", "investors.manager_id"]
        ),
        sa.UniqueConstraint("document_id", "investor_id"),
    )


def downgrade():
    raise RuntimeError("投资者主体、资料关系和访问边界不可通过回滚删除；请使用验证过的备份")
