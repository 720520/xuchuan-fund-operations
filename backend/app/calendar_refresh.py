"""Periodically verify bundled calendar data against authoritative source pages."""

import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from urllib.request import Request, urlopen

from .trading_calendar import PUBLIC_HOLIDAY_SOURCES, SOURCES, VERSION


CHECK_INTERVAL = timedelta(days=30)
RETRY_INTERVAL = timedelta(days=1)


class _VisibleText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag.lower() in {"style", "script", "head", "template"}:
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag.lower() in {"style", "script", "head", "template"} and self.hidden:
            self.hidden -= 1

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def _cache_path(settings):
    return settings.storage.parent / "calendar-source-check.json"


def read_status(settings):
    path = _cache_path(settings)
    if not path.is_file():
        return {
            "status": "bundled",
            "checked_at": None,
            "next_check_at": None,
            "calendar_version": VERSION,
        }
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {
            "status": "bundled",
            "checked_at": None,
            "next_check_at": None,
            "calendar_version": VERSION,
        }


def _source_text(url, opener):
    response = opener(
        Request(url, headers={"User-Agent": "Xuchuan-Calendar-Check/0.1"}),
        timeout=20,
    )
    try:
        content = response.read(2 * 1024 * 1024 + 1)
    finally:
        close = getattr(response, "close", None)
        if close:
            close()
    if len(content) > 2 * 1024 * 1024:
        raise ValueError("官方日历页面超过校验大小限制")
    parser = _VisibleText()
    parser.feed(content.decode("utf-8", errors="replace"))
    return " ".join(parser.parts)


def refresh_official_sources(settings, *, force=False, opener=urlopen, at=None):
    at = at or datetime.now(timezone.utc)
    previous = read_status(settings)
    next_check = previous.get("next_check_at")
    if not force and next_check and datetime.fromisoformat(next_check) > at:
        return previous
    checks = []
    try:
        for kind, sources, marker in (
            ("trading", SOURCES, "休市"),
            ("public_holiday", PUBLIC_HOLIDAY_SOURCES, "节假日"),
        ):
            for year, url in sources.items():
                text = _source_text(url, opener)
                if str(year) not in text or marker not in text:
                    raise ValueError(f"{year} 年官方{kind}页面内容无法识别")
                checks.append(
                    {
                        "kind": kind,
                        "year": year,
                        "url": url,
                        "sha256": hashlib.sha256(text.encode()).hexdigest(),
                    }
                )
        prior_hashes = {
            (item["kind"], item["year"]): item["sha256"]
            for item in previous.get("checks", [])
        }
        changed = any(
            prior_hashes
            and prior_hashes.get((item["kind"], item["year"])) != item["sha256"]
            for item in checks
        )
        result = {
            "status": "review" if changed else "verified",
            "checked_at": at.isoformat(),
            "next_check_at": (at + CHECK_INTERVAL).isoformat(),
            "calendar_version": VERSION,
            "change_detected": changed,
            "checks": checks,
        }
    except Exception as exc:  # external page failures never alter business dates
        result = {
            **previous,
            "status": "unavailable",
            "last_attempt_at": at.isoformat(),
            "next_check_at": (at + RETRY_INTERVAL).isoformat(),
            "error": f"官方日历检查失败（{type(exc).__name__}），继续使用最后确认版本",
            "calendar_version": VERSION,
        }
    path = _cache_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    os.replace(temporary, path)
    return result
