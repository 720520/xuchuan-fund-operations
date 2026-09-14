"""Add structured investor profiles, material types and bank accounts."""

from alembic import op
import sqlalchemy as sa


revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "document_materials",
        sa.Column("material_type", sa.String(50), nullable=True),
    )
    for _, column in [
        ("suitability_class", sa.Column("suitability_class", sa.String(20), nullable=False, server_default="unknown")),
        ("professional_investor_type", sa.Column("professional_investor_type", sa.String(100), nullable=True)),
        ("certificate_type", sa.Column("certificate_type", sa.String(50), nullable=True)),
        ("certificate_number_ciphertext", sa.Column("certificate_number_ciphertext", sa.Text(), nullable=True)),
        ("certificate_number_masked", sa.Column("certificate_number_masked", sa.String(100), nullable=True)),
        ("certificate_valid_until", sa.Column("certificate_valid_until", sa.String(10), nullable=True)),
        ("nationality_or_region", sa.Column("nationality_or_region", sa.String(100), nullable=True)),
        ("contact_email", sa.Column("contact_email", sa.String(254), nullable=True)),
        ("contact_phone", sa.Column("contact_phone", sa.String(50), nullable=True)),
        ("specific_object_status", sa.Column("specific_object_status", sa.String(20), nullable=False, server_default="unknown")),
        ("specific_object_confirmed_at", sa.Column("specific_object_confirmed_at", sa.String(10), nullable=True)),
        ("risk_level", sa.Column("risk_level", sa.String(30), nullable=True)),
        ("risk_assessed_at", sa.Column("risk_assessed_at", sa.String(10), nullable=True)),
        ("risk_expires_at", sa.Column("risk_expires_at", sa.String(10), nullable=True)),
        ("qualified_material_status", sa.Column("qualified_material_status", sa.String(20), nullable=False, server_default="unknown")),
        ("qualified_material_from", sa.Column("qualified_material_from", sa.String(10), nullable=True)),
        ("qualified_material_until", sa.Column("qualified_material_until", sa.String(10), nullable=True)),
        ("profile_source_document_id", sa.Column("profile_source_document_id", sa.String(36), nullable=True)),
        ("suitability_source_document_id", sa.Column("suitability_source_document_id", sa.String(36), nullable=True)),
    ]:
        op.add_column("investors", column)

    op.create_table(
        "investor_bank_accounts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("manager_id", sa.String(36), nullable=False),
        sa.Column("investor_id", sa.String(36), nullable=False),
        sa.Column("account_name", sa.String(200), nullable=False),
        sa.Column("account_number_ciphertext", sa.Text(), nullable=False),
        sa.Column("account_number_masked", sa.String(100), nullable=False),
        sa.Column("bank_name", sa.String(200), nullable=False),
        sa.Column("branch_name", sa.String(300), nullable=False),
        sa.Column("currency", sa.String(10), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("source_document_id", sa.String(36), nullable=True),
        sa.Column("created_by", sa.String(36), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["investor_id", "manager_id"], ["investors.id", "investors.manager_id"]
        ),
        sa.ForeignKeyConstraint(
            ["source_document_id", "manager_id"], ["documents.id", "documents.manager_id"]
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.UniqueConstraint("id", "manager_id"),
    )
    op.create_index(
        "ix_investor_bank_accounts_manager_id",
        "investor_bank_accounts",
        ["manager_id"],
    )
    op.create_table(
        "investor_bank_account_products",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("manager_id", sa.String(36), nullable=False),
        sa.Column("bank_account_id", sa.String(36), nullable=False),
        sa.Column("product_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.ForeignKeyConstraint(
            ["bank_account_id", "manager_id"],
            ["investor_bank_accounts.id", "investor_bank_accounts.manager_id"],
        ),
        sa.ForeignKeyConstraint(
            ["product_id", "manager_id"], ["products.id", "products.manager_id"]
        ),
        sa.UniqueConstraint("bank_account_id", "product_id"),
    )


def downgrade():
    raise RuntimeError("投资者敏感字段和账户资料不可通过回滚删除；请使用验证过的备份")
