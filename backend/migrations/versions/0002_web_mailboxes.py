"""Web-managed encrypted mailbox credentials and folder-aware receipts."""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "mailboxes",
        sa.Column("host", sa.String(253), nullable=False, server_default=""),
    )
    op.add_column(
        "mailboxes",
        sa.Column("port", sa.Integer(), nullable=False, server_default="993"),
    )
    op.add_column(
        "mailboxes",
        sa.Column("tls", sa.String(10), nullable=False, server_default="ssl"),
    )
    op.add_column(
        "mailboxes",
        sa.Column("username", sa.String(254), nullable=False, server_default=""),
    )
    op.add_column(
        "mailboxes", sa.Column("credential_ciphertext", sa.Text(), nullable=True)
    )
    op.add_column(
        "mailboxes",
        sa.Column(
            "all_folders", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.add_column(
        "mailboxes",
        sa.Column("send_id", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    bind = op.get_bind()
    existing = next(
        constraint
        for constraint in sa.inspect(bind).get_unique_constraints("mail_receipts")
        if set(constraint["column_names"])
        == {"mailbox_id", "uid_validity", "message_uid"}
    )
    convention = {"uq": "uq_%(table_name)s_%(column_0_name)s"}
    with op.batch_alter_table("mail_receipts", naming_convention=convention) as batch:
        batch.add_column(
            sa.Column("folder", sa.String(255), nullable=False, server_default="INBOX")
        )
        batch.drop_constraint(
            existing["name"] or "uq_mail_receipts_mailbox_id", type_="unique"
        )
        batch.create_unique_constraint(
            "uq_mail_receipts_mailbox_folder_uid",
            ["mailbox_id", "folder", "uid_validity", "message_uid"],
        )


def downgrade():
    raise RuntimeError("邮件证据迁移不可回滚；请从经过验证的备份恢复")
