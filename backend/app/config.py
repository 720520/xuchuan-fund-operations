import os
from dataclasses import dataclass, field
from pathlib import Path


def upload_limit():
    value = int(os.getenv("MAX_UPLOAD_MIB", "25"))
    if value < 1 or value > 500:
        raise ValueError("MAX_UPLOAD_MIB 必须在 1 到 500 之间")
    return value * 1024 * 1024


@dataclass(frozen=True)
class Settings:
    database_url: str = field(
        default_factory=lambda: os.getenv(
            "DATABASE_URL", "sqlite:///./runtime/development.db"
        )
    )
    storage: Path = field(
        default_factory=lambda: Path(os.getenv("ARCHIVE_DIR", "./runtime/archive"))
    )
    mail_key_file: Path = field(
        default_factory=lambda: Path(
            os.getenv("MAIL_KEY_FILE", "./runtime/private/mail-encryption.key")
        )
    )
    cookie_secure: bool = field(
        default_factory=lambda: os.getenv("COOKIE_SECURE", "true").lower() == "true"
    )
    origins: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            s.strip()
            for s in os.getenv(
                "ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
            ).split(",")
            if s.strip()
        )
    )
    session_hours: int = 8
    max_upload: int = field(default_factory=upload_limit)
    max_rows: int = 10000
