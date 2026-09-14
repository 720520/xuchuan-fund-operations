from datetime import date, datetime, timezone

from app.calendar_refresh import refresh_official_sources
from app.trading_calendar import is_makeup_workday, month_days, public_holiday
from conftest import login


def test_calendar_api_shows_trading_holidays_and_makeup_days(env):
    _, client, ids = env
    login(client)
    response = client.get(f"/api/managers/{ids['a']}/calendar?month=2026-09")
    assert response.status_code == 200, response.text
    days = {item["date"]: item for item in response.json()["days"]}
    assert days["2026-09-09"]["trading_day"]
    assert "open_days" not in days["2026-09-09"]
    assert days["2026-09-25"]["holiday_name"] == "中秋节"
    assert not days["2026-09-25"]["trading_day"]
    assert days["2026-09-20"]["makeup_workday"]
    assert not days["2026-09-20"]["trading_day"]


def test_calendar_helpers_and_invalid_month(env):
    _, client, ids = env
    assert len(month_days(2026, 2)) == 28
    assert public_holiday(date(2026, 10, 3)) == "国庆节"
    assert is_makeup_workday(date(2026, 10, 10))
    login(client)
    assert client.get(f"/api/managers/{ids['a']}/calendar?month=2026-13").status_code == 422
    assert client.get(f"/api/managers/{ids['a']}/calendar?month=2027-01").status_code == 422


class FakeResponse:
    def __init__(self, content):
        self.content = content.encode()
        self.closed = False

    def read(self, _limit):
        return self.content

    def close(self):
        self.closed = True


def test_official_calendar_sources_are_cached_and_changes_require_review(env):
    app, _, _ = env
    calls = []

    def opener(request, timeout):
        calls.append((request.full_url, timeout))
        year = "2025" if "2024" in request.full_url or "202411" in request.full_url else "2026"
        marker = "节假日" if "gov.cn" in request.full_url else "休市"
        return FakeResponse(f"<html><body>{year} 年 {marker} 安排</body></html>")

    checked_at = datetime(2026, 9, 8, tzinfo=timezone.utc)
    first = refresh_official_sources(
        app.state.settings, force=True, opener=opener, at=checked_at
    )
    assert first["status"] == "verified"
    assert len(calls) == 4
    cached = refresh_official_sources(
        app.state.settings, opener=opener, at=checked_at
    )
    assert cached == first
    assert len(calls) == 4

    def changed_opener(request, timeout):
        response = opener(request, timeout)
        if "gov.cn" in request.full_url and "202511" in request.full_url:
            response.content += " 页面修订".encode()
        return response

    changed = refresh_official_sources(
        app.state.settings, force=True, opener=changed_opener, at=checked_at
    )
    assert changed["status"] == "review"
    assert changed["change_detected"] is True
