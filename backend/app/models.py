from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)

from .db import Base, now, uid


class Group(Base):
    __tablename__ = "groups"
    id = Column(String(36), primary_key=True, default=uid)
    name = Column(String(150), nullable=False)


class Manager(Base):
    __tablename__ = "managers"
    id = Column(String(36), primary_key=True, default=uid)
    group_id = Column(ForeignKey("groups.id"), nullable=False, index=True)
    name = Column(String(150), nullable=False)
    __table_args__ = (UniqueConstraint("group_id", "name"),)


class User(Base):
    __tablename__ = "users"
    id = Column(String(36), primary_key=True, default=uid)
    email = Column(String(254), nullable=False, unique=True)
    name = Column(String(80), nullable=False)
    password_hash = Column(Text, nullable=False)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(String(40), default=now, nullable=False)


class Membership(Base):
    __tablename__ = "memberships"
    id = Column(String(36), primary_key=True, default=uid)
    user_id = Column(ForeignKey("users.id"), nullable=False)
    manager_id = Column(ForeignKey("managers.id"), nullable=False)
    roles = Column(JSON, nullable=False, default=list)
    can_download = Column(Boolean, default=False, nullable=False)
    __table_args__ = (UniqueConstraint("user_id", "manager_id"),)


class Session(Base):
    __tablename__ = "sessions"
    token_hash = Column(String(64), primary_key=True)
    user_id = Column(ForeignKey("users.id"), nullable=False)
    expires_at = Column(String(40), nullable=False)


class LoginAttempt(Base):
    __tablename__ = "login_attempts"
    key = Column(String(64), primary_key=True)
    failures = Column(Integer, default=0, nullable=False)
    blocked_until = Column(String(40), nullable=True)


class Product(Base):
    __tablename__ = "products"
    id = Column(String(36), primary_key=True, default=uid)
    manager_id = Column(ForeignKey("managers.id"), nullable=False, index=True)
    code = Column(String(80), nullable=False)
    name = Column(String(200), nullable=False)
    currency = Column(String(8), default="CNY", nullable=False)
    strategy = Column(String(80), default="", nullable=False)
    expected = Column(Boolean, default=True, nullable=False)
    frequency = Column(String(12), default="daily", nullable=False)
    weekday = Column(Integer, default=4, nullable=False)
    cutoff = Column(String(5), default="11:00", nullable=False)
    lifecycle_status = Column(String(20), default="active", nullable=False)
    lifecycle_date = Column(String(10), nullable=True)
    lifecycle_reason = Column(Text, nullable=True)
    lifecycle_updated_at = Column(String(40), nullable=True)
    # Actor referential integrity is preserved in append-only audit_events; keeping
    # this denormalized id avoids rebuilding SQLite's heavily referenced table.
    lifecycle_updated_by = Column(String(36), nullable=True)
    created_at = Column(String(40), default=now, nullable=False)
    __table_args__ = (
        UniqueConstraint("manager_id", "code"),
        UniqueConstraint("id", "manager_id"),
    )


class ProductFiling(Base):
    __tablename__ = "product_filings"
    id = Column(String(36), primary_key=True, default=uid)
    manager_id = Column(ForeignKey("managers.id"), nullable=False, index=True)
    code = Column(String(80), nullable=False)
    name = Column(String(200), nullable=False)
    currency = Column(String(8), default="CNY", nullable=False)
    strategy = Column(String(80), default="", nullable=False)
    shares = Column(JSON, nullable=False, default=list)
    status = Column(String(20), default="in_progress", nullable=False)
    created_by = Column(ForeignKey("users.id"), nullable=False)
    product_id = Column(ForeignKey("products.id"), nullable=True)
    created_at = Column(String(40), default=now, nullable=False)
    completed_at = Column(String(40), nullable=True)


class ShareClass(Base):
    __tablename__ = "share_classes"
    id = Column(String(36), primary_key=True, default=uid)
    product_id = Column(String(36), nullable=False)
    manager_id = Column(String(36), nullable=False)
    name = Column(String(80), nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(
            ["product_id", "manager_id"], ["products.id", "products.manager_id"]
        ),
        UniqueConstraint("product_id", "name"),
        UniqueConstraint("id", "manager_id", "product_id"),
    )


class ProductGrant(Base):
    __tablename__ = "product_grants"
    id = Column(String(36), primary_key=True, default=uid)
    user_id = Column(ForeignKey("users.id"), nullable=False)
    product_id = Column(ForeignKey("products.id"), nullable=False)
    __table_args__ = (UniqueConstraint("user_id", "product_id"),)


class ValidationRule(Base):
    __tablename__ = "validation_rules"
    manager_id = Column(ForeignKey("managers.id"), primary_key=True)
    max_nav_change = Column(Numeric(10, 6), nullable=True)
    updated_at = Column(String(40), default=now, nullable=False)


class Document(Base):
    __tablename__ = "documents"
    id = Column(String(36), primary_key=True, default=uid)
    manager_id = Column(ForeignKey("managers.id"), nullable=False, index=True)
    product_id = Column(String(36), nullable=True)
    filename = Column(String(255), nullable=False)
    sha256 = Column(String(64), nullable=False)
    storage_key = Column(String(200), nullable=False)
    size = Column(Integer, nullable=False)
    media_type = Column(String(100), nullable=False)
    source = Column(String(30), nullable=False)
    uploader_id = Column(ForeignKey("users.id"), nullable=True)
    parent_id = Column(String(36), nullable=True)
    received_at = Column(String(40), default=now, nullable=False)
    metadata_json = Column(JSON, default=dict, nullable=False)
    __table_args__ = (
        UniqueConstraint("id", "manager_id"),
        ForeignKeyConstraint(
            ["product_id", "manager_id"], ["products.id", "products.manager_id"]
        ),
        ForeignKeyConstraint(
            ["parent_id", "manager_id"], ["documents.id", "documents.manager_id"]
        ),
    )


class ParseJob(Base):
    __tablename__ = "parse_jobs"
    id = Column(String(36), primary_key=True, default=uid)
    manager_id = Column(ForeignKey("managers.id"), nullable=False)
    document_id = Column(String(36), nullable=False, unique=True)
    status = Column(String(20), default="queued", nullable=False)
    result = Column(JSON, default=dict, nullable=False)
    updated_at = Column(String(40), default=now, nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(
            ["document_id", "manager_id"], ["documents.id", "documents.manager_id"]
        ),
    )


class NavRecord(Base):
    __tablename__ = "nav_records"
    id = Column(String(36), primary_key=True, default=uid)
    manager_id = Column(String(36), nullable=False, index=True)
    product_id = Column(String(36), nullable=False)
    share_id = Column(String(36), nullable=False)
    valuation_date = Column(String(10), nullable=False)
    unit_nav = Column(Numeric(24, 10), nullable=False)
    accumulated_nav = Column(Numeric(24, 10), nullable=True)
    net_assets = Column(Numeric(30, 4), nullable=True)
    total_shares = Column(Numeric(30, 4), nullable=True)
    source = Column(String(30), nullable=False)
    document_id = Column(String(36), nullable=True)
    actor_id = Column(ForeignKey("users.id"), nullable=True)
    received_at = Column(String(40), default=now, nullable=False)
    row_key = Column(String(100), nullable=True)
    reported_metrics = Column(JSON, default=dict, nullable=False)
    validation = Column(JSON, default=list, nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(
            ["share_id", "manager_id", "product_id"],
            [
                "share_classes.id",
                "share_classes.manager_id",
                "share_classes.product_id",
            ],
        ),
        ForeignKeyConstraint(
            ["document_id", "manager_id"], ["documents.id", "documents.manager_id"]
        ),
        UniqueConstraint("id", "manager_id", "share_id", "valuation_date"),
        UniqueConstraint("document_id", "row_key"),
    )


class EffectiveNav(Base):
    __tablename__ = "effective_nav"
    manager_id = Column(ForeignKey("managers.id"), nullable=False)
    share_id = Column(ForeignKey("share_classes.id"), primary_key=True)
    valuation_date = Column(String(10), primary_key=True)
    record_id = Column(String(36), nullable=False)
    reversal = Column(Boolean, default=False, nullable=False)
    revision = Column(Integer, default=1, nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(
            ["record_id", "manager_id", "share_id", "valuation_date"],
            [
                "nav_records.id",
                "nav_records.manager_id",
                "nav_records.share_id",
                "nav_records.valuation_date",
            ],
        ),
    )


class ExceptionTask(Base):
    __tablename__ = "exception_tasks"
    id = Column(String(36), primary_key=True, default=uid)
    manager_id = Column(ForeignKey("managers.id"), nullable=False, index=True)
    product_id = Column(String(36), nullable=True)
    share_id = Column(ForeignKey("share_classes.id"), nullable=True)
    valuation_date = Column(String(10), nullable=True)
    kind = Column(String(30), nullable=False)
    dedup_key = Column(String(250), nullable=False)
    status = Column(String(20), default="open", nullable=False)
    assignee_id = Column(ForeignKey("users.id"), nullable=True)
    payload = Column(JSON, default=dict, nullable=False)
    resolution = Column(JSON, nullable=True)
    created_at = Column(String(40), default=now, nullable=False)
    updated_at = Column(String(40), default=now, nullable=False)
    revision = Column(Integer, default=1, nullable=False)
    __table_args__ = (
        UniqueConstraint("manager_id", "dedup_key"),
        ForeignKeyConstraint(
            ["product_id", "manager_id"], ["products.id", "products.manager_id"]
        ),
    )


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id = Column(String(36), primary_key=True, default=uid)
    manager_id = Column(ForeignKey("managers.id"), nullable=False, index=True)
    actor_id = Column(ForeignKey("users.id"), nullable=True)
    action = Column(String(80), nullable=False)
    object_id = Column(String(36), nullable=False)
    details = Column(JSON, default=dict, nullable=False)
    created_at = Column(String(40), default=now, nullable=False)


class Mailbox(Base):
    __tablename__ = "mailboxes"
    id = Column(String(36), primary_key=True, default=uid)
    manager_id = Column(ForeignKey("managers.id"), nullable=False)
    label = Column(String(100), nullable=False)
    env_prefix = Column(String(80), nullable=False, unique=True)
    host = Column(String(253), default="", nullable=False)
    port = Column(Integer, default=993, nullable=False)
    tls = Column(String(10), default="ssl", nullable=False)
    username = Column(String(254), default="", nullable=False)
    credential_ciphertext = Column(Text, nullable=True)
    all_folders = Column(Boolean, default=False, nullable=False)
    send_id = Column(Boolean, default=False, nullable=False)
    since = Column(String(10), nullable=False)
    enabled = Column(Boolean, default=False, nullable=False)
    last_sync = Column(String(40), nullable=True)
    error = Column(String(200), nullable=True)


class MailReceipt(Base):
    __tablename__ = "mail_receipts"
    id = Column(String(36), primary_key=True, default=uid)
    mailbox_id = Column(ForeignKey("mailboxes.id"), nullable=False)
    folder = Column(String(255), default="INBOX", nullable=False)
    uid_validity = Column(String(40), nullable=False)
    message_uid = Column(String(40), nullable=False)
    document_id = Column(ForeignKey("documents.id"), nullable=False)
    __table_args__ = (
        UniqueConstraint("mailbox_id", "folder", "uid_validity", "message_uid"),
    )


Index(
    "ix_nav_lookup", NavRecord.manager_id, NavRecord.share_id, NavRecord.valuation_date
)
