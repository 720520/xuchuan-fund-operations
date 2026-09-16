from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Login(Strict):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)

    model_config = ConfigDict(extra="forbid")  # Password spaces are significant.


class ProductCreate(Strict):
    code: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=200)
    currency: str = Field(default="CNY", pattern=r"^[A-Z]{3}$")
    strategy: str = Field(default="", max_length=80)
    shares: list[str] = Field(min_length=1, max_length=30)

    @field_validator("shares")
    @classmethod
    def clean_shares(cls, value):
        value = [s.strip() for s in value]
        if any(not s or len(s) > 80 for s in value) or len(set(value)) != len(value):
            raise ValueError("份额名称不能为空、重复或超过 80 字")
        return value


class Schedule(Strict):
    expected: bool
    frequency: Literal["daily", "weekly", "off"]
    weekday: int = Field(default=4, ge=0, le=6)
    cutoff: str = Field(default="15:00", pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")


class ShareCreate(Strict):
    name: str = Field(min_length=1, max_length=80)


class NavInput(Strict):
    product_id: str
    share_id: str
    valuation_date: date
    unit_nav: str = Field(min_length=1, max_length=60)
    accumulated_nav: str | None = Field(default=None, max_length=60)
    net_assets: str | None = Field(default=None, max_length=60)
    total_shares: str | None = Field(default=None, max_length=60)


class Revision(Strict):
    revision: int = Field(ge=1)


class Resolution(Revision):
    record_id: str
    reversal: bool = False
    reason: str = Field(default="", max_length=2000)


class Assign(Revision):
    user_id: str | None = None
    reason: str = Field(min_length=1, max_length=2000)


class ManualCompletion(Revision):
    reason: str = Field(min_length=1, max_length=2000)
    complete_material: Literal[True]
    records: list[NavInput] = Field(min_length=1, max_length=100)


class Access(Strict):
    roles: list[str] = Field(max_length=10)
    can_download: bool = False
    product_ids: list[str] = Field(default_factory=list, max_length=500)


class UserCreate(Access):
    email: str = Field(min_length=3, max_length=254)
    name: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=12, max_length=128)
    model_config = ConfigDict(extra="forbid")


class PasswordChange(Strict):
    old_password: str = Field(max_length=128)
    new_password: str = Field(min_length=12, max_length=128)
    model_config = ConfigDict(extra="forbid")


class MailboxCreate(Strict):
    label: str = Field(min_length=1, max_length=100)
    host: str = Field(min_length=1, max_length=253, pattern=r"^[A-Za-z0-9.-]+$")
    port: int = Field(ge=1, le=65535)
    tls: Literal["ssl", "starttls"]
    username: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=512)
    since: date
    all_folders: bool = True
    send_id: bool = False
    enabled: bool = True

    model_config = ConfigDict(
        extra="forbid"
    )  # Authorization-code spaces are significant.

    @field_validator("label", "host", "username")
    @classmethod
    def clean_mailbox_text(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("邮箱名称、服务器和账号不能为空")
        return value


class MailboxUpdate(Strict):
    label: str = Field(min_length=1, max_length=100)
    host: str = Field(min_length=1, max_length=253, pattern=r"^[A-Za-z0-9.-]+$")
    port: int = Field(ge=1, le=65535)
    tls: Literal["ssl", "starttls"]
    username: str = Field(min_length=1, max_length=254)
    password: str | None = Field(default=None, min_length=1, max_length=512)
    since: date
    all_folders: bool = True
    send_id: bool = False
    enabled: bool = True

    model_config = ConfigDict(
        extra="forbid"
    )  # Authorization-code spaces are significant.

    @field_validator("label", "host", "username")
    @classmethod
    def clean_mailbox_text(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("邮箱名称、服务器和账号不能为空")
        return value


class MailActionCompletion(Revision):
    reason: str = Field(min_length=1, max_length=2000)


class MailClassification(Revision):
    category: Literal[
        "nav_valuation",
        "futures_settlement",
        "reconciliation_data",
        "risk_monitoring",
        "open_day_calendar",
        "contract_seal",
        "investor_redemption",
        "security",
        "action_required",
        "completion_receipt",
        "marketing",
        "other",
    ]
    handling_mode: Literal["task", "receipt", "archive"]
    suggested_action: str | None = Field(default=None, max_length=500)


class ExceptionMailDisposition(Revision):
    disposition: Literal["notification", "duplicate", "void"]
    reason: str = Field(min_length=1, max_length=2000)


class RuleInput(Strict):
    max_nav_change: str | None = Field(default=None, max_length=20)


class ReceiptPolicyInput(Strict):
    enabled: bool
    start_date: date
    followup_time: str = Field(default="09:00", pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    calendar_confirmed: Literal[True]


class ReceiptFollowup(Revision):
    reason: str = Field(min_length=1, max_length=2000)


class MaterialReceived(ReceiptFollowup):
    document_id: str


class MaterialOrganization(Strict):
    revision: int = Field(default=0, ge=0)
    category: Literal[
        "nav_valuation",
        "contract",
        "investor_qualification",
        "subscription_redemption",
        "filing",
        "custody_account",
        "periodic_report",
        "risk_compliance",
        "operation_evidence",
        "other",
    ]
    material_type: Literal[
        "qualified_investor_commitment",
        "risk_questionnaire",
        "investor_information_form",
        "identity_front",
        "identity_back",
        "identity_document",
        "asset_proof",
        "tax_declaration",
        "professional_investor_proof",
        "institution_certificate",
        "representative_identity",
        "authorization",
        "product_filing_certificate",
        "bank_account_proof",
        "special_object_confirmation",
        "contract",
        "risk_disclosure",
        "supplemental_agreement",
        "subscription_form",
        "redemption_form",
        "share_confirmation",
        "position_statement",
        "dividend_notice",
        "double_recording",
        "cooling_off_callback",
        "transfer_voucher",
        "custom",
    ] | None = None
    title: str | None = Field(default=None, max_length=500)
    business_date: date | None = None
    period_start: date | None = None
    period_end: date | None = None
    product_ids: list[str] = Field(default_factory=list, max_length=500)
    investor_ids: list[str] = Field(default_factory=list, max_length=500)
    sensitivity: Literal["standard", "investor_sensitive"] = "standard"
    notes: str = Field(default="", max_length=2000)
    confirmed: Literal[True]

    @field_validator("product_ids")
    @classmethod
    def unique_products(cls, value):
        if any(not item for item in value) or len(set(value)) != len(value):
            raise ValueError("关联产品不能为空或重复")
        return value

    @field_validator("investor_ids")
    @classmethod
    def unique_investors(cls, value):
        if any(not item for item in value) or len(set(value)) != len(value):
            raise ValueError("关联投资者不能为空或重复")
        return value

    @model_validator(mode="after")
    def valid_period(self):
        if self.period_end and not self.period_start:
            raise ValueError("填写期间结束日时必须填写开始日")
        if self.period_start and self.period_end and self.period_end < self.period_start:
            raise ValueError("资料期间结束日不能早于开始日")
        return self


class InvestorSave(Strict):
    revision: int = Field(default=0, ge=0)
    investor_type: Literal[
        "individual",
        "institution",
        "fund_product",
        "asset_management",
        "manager_co_investment",
        "other",
    ]
    display_name: str = Field(min_length=1, max_length=200)
    suitability_class: Literal["ordinary", "professional", "unknown"] = "unknown"
    professional_investor_type: str | None = Field(default=None, max_length=100)
    certificate_type: str | None = Field(default=None, max_length=50)
    certificate_number: str | None = Field(default=None, min_length=4, max_length=100)
    clear_certificate_number: bool = False
    certificate_valid_until: date | None = None
    nationality_or_region: str | None = Field(default=None, max_length=100)
    contact_email: str | None = Field(default=None, max_length=254)
    contact_phone: str | None = Field(default=None, max_length=50)
    specific_object_status: Literal["unknown", "pending", "confirmed", "expired", "not_applicable"] = "unknown"
    specific_object_confirmed_at: date | None = None
    risk_level: str | None = Field(default=None, max_length=30)
    risk_assessed_at: date | None = None
    risk_expires_at: date | None = None
    qualified_material_status: Literal["unknown", "missing", "valid", "expired", "not_applicable"] = "unknown"
    qualified_material_from: date | None = None
    qualified_material_until: date | None = None
    profile_source_document_id: str | None = None
    suitability_source_document_id: str | None = None
    status: Literal["pending", "confirmed", "historical"] = "pending"
    source: Literal["manual", "directory_reference", "material"] = "manual"
    product_ids: list[str] = Field(default_factory=list, max_length=500)
    notes: str = Field(default="", max_length=2000)

    @field_validator("product_ids")
    @classmethod
    def unique_investor_products(cls, value):
        if any(not item for item in value) or len(set(value)) != len(value):
            raise ValueError("关联产品不能为空或重复")
        return value

    @model_validator(mode="after")
    def valid_investor_dates(self):
        if self.risk_assessed_at and self.risk_expires_at and self.risk_expires_at < self.risk_assessed_at:
            raise ValueError("风险测评到期日不能早于测评日期")
        if self.qualified_material_from and self.qualified_material_until and self.qualified_material_until < self.qualified_material_from:
            raise ValueError("合格材料到期日不能早于建立日期")
        if self.suitability_class != "professional" and self.professional_investor_type:
            raise ValueError("只有专业投资者可以填写专业投资者类型")
        return self


class InvestorBankAccountSave(Strict):
    revision: int = Field(default=0, ge=0)
    account_name: str = Field(min_length=1, max_length=200)
    account_number: str | None = Field(default=None, min_length=4, max_length=100)
    bank_name: str = Field(min_length=1, max_length=200)
    branch_name: str = Field(default="", max_length=300)
    currency: str = Field(default="CNY", min_length=3, max_length=10)
    status: Literal["active", "inactive"] = "active"
    source_document_id: str | None = None
    product_ids: list[str] = Field(default_factory=list, max_length=500)

    @field_validator("product_ids")
    @classmethod
    def unique_bank_products(cls, value):
        if any(not item for item in value) or len(set(value)) != len(value):
            raise ValueError("账户关联产品不能为空或重复")
        return value


class InvestorShareEventCreate(Strict):
    product_id: str
    share_id: str | None = None
    event_type: Literal[
        "subscription",
        "additional_subscription",
        "redemption",
        "full_redemption",
        "cash_dividend",
        "dividend_reinvestment",
        "transfer",
        "adjustment",
    ]
    evidence_stage: Literal["notice", "application", "accepted", "confirmation"] = "notice"
    application_date: date | None = None
    confirmation_date: date | None = None
    effective_date: date | None = None
    requested_amount: str | None = Field(default=None, max_length=60)
    confirmed_amount: str | None = Field(default=None, max_length=60)
    units_delta: str | None = Field(default=None, max_length=60)
    unit_nav: str | None = Field(default=None, max_length=60)
    fee_amount: str | None = Field(default=None, max_length=60)
    balance_after: str | None = Field(default=None, max_length=60)
    business_ref: str | None = Field(default=None, max_length=150)
    source_mail_item_id: str | None = None
    source_document_id: str | None = None
    supersedes_event_id: str | None = None
    notes: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def valid_share_event(self):
        if self.evidence_stage == "confirmation" and not (
            self.confirmation_date or self.effective_date
        ):
            raise ValueError("确认材料需要填写确认日或生效日")
        return self


class InvestorShareEventStatus(Strict):
    revision: int = Field(ge=1)
    status: Literal["confirmed", "archived", "void"]
    reason: str = Field(min_length=1, max_length=2000)


class InvestorPositionSnapshotCreate(Strict):
    product_id: str
    share_id: str | None = None
    as_of_date: date
    units: str = Field(min_length=1, max_length=60)
    source_mail_item_id: str | None = None
    source_document_id: str | None = None
    notes: str = Field(default="", max_length=2000)
