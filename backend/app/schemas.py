from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


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
    cutoff: str = Field(default="11:00", pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")


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


class RuleInput(Strict):
    max_nav_change: str | None = Field(default=None, max_length=20)
