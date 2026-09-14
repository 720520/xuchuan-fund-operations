"""Verified SSE and public-holiday calendar; unsupported years fail closed."""
from calendar import monthrange
from datetime import date, timedelta

VERSION = "SSE-2025-2026-v1"
SOURCES = {
    2025: "https://www.sse.com.cn/disclosure/announcement/general/c/c_20241223_10767108.shtml",
    2026: "https://www.sse.com.cn/disclosure/announcement/general/c/c_20251222_10802507.shtml",
}
PUBLIC_HOLIDAY_SOURCES = {
    2025: "https://www.gov.cn/zhengce/zhengceku/202411/content_6986383.htm",
    2026: "https://www.gov.cn/gongbao/2025/issue_12406/202511/content_7048922.html",
}
CLOSURES = {
    2025: [("01-01", "01-01"), ("01-28", "02-04"), ("04-04", "04-06"),
           ("05-01", "05-05"), ("05-31", "06-02"), ("10-01", "10-08")],
    2026: [("01-01", "01-03"), ("02-15", "02-23"), ("04-04", "04-06"),
           ("05-01", "05-05"), ("06-19", "06-21"), ("09-25", "09-27"),
           ("10-01", "10-07")],
}
PUBLIC_HOLIDAYS = {
    2025: [
        ("01-01", "01-01", "元旦"),
        ("01-28", "02-04", "春节"),
        ("04-04", "04-06", "清明节"),
        ("05-01", "05-05", "劳动节"),
        ("05-31", "06-02", "端午节"),
        ("10-01", "10-08", "国庆节、中秋节"),
    ],
    2026: [
        ("01-01", "01-03", "元旦"),
        ("02-15", "02-23", "春节"),
        ("04-04", "04-06", "清明节"),
        ("05-01", "05-05", "劳动节"),
        ("06-19", "06-21", "端午节"),
        ("09-25", "09-27", "中秋节"),
        ("10-01", "10-07", "国庆节"),
    ],
}
MAKEUP_WORKDAYS = {
    2025: {"01-26", "02-08", "04-27", "09-28", "10-11"},
    2026: {"01-04", "02-14", "02-28", "05-09", "09-20", "10-10"},
}


class CalendarUnavailable(ValueError):
    pass


def is_trading_day(day: date) -> bool:
    if day.year not in CLOSURES:
        raise CalendarUnavailable(f"交易日历未覆盖 {day.year} 年，请更新日历后继续自动检查")
    return day.weekday() < 5 and not any(
        begin <= day.strftime("%m-%d") <= end for begin, end in CLOSURES[day.year]
    )


def public_holiday(day: date) -> str | None:
    key = day.strftime("%m-%d")
    for begin, end, name in PUBLIC_HOLIDAYS.get(day.year, []):
        if begin <= key <= end:
            return name
    return None


def is_makeup_workday(day: date) -> bool:
    return day.strftime("%m-%d") in MAKEUP_WORKDAYS.get(day.year, set())


def month_days(year: int, month: int):
    if year not in CLOSURES:
        raise CalendarUnavailable(f"交易日历未覆盖 {year} 年，请更新日历后继续查看")
    return [date(year, month, number) for number in range(1, monthrange(year, month)[1] + 1)]


def previous_trading_day(day: date) -> date:
    day -= timedelta(days=1)
    while not is_trading_day(day):
        day -= timedelta(days=1)
    return day


def next_trading_day(day: date) -> date:
    day += timedelta(days=1)
    while not is_trading_day(day):
        day += timedelta(days=1)
    return day


def expected_on(product, valuation_day: date) -> bool:
    if not product.expected or product.frequency == "off" or not is_trading_day(valuation_day):
        return False
    if product.frequency == "daily":
        return True
    # Weekly weekday denotes the valuation weekday; a closure rolls back to the
    # preceding trading day. Each week therefore has exactly one expected NAV.
    anchor = valuation_day + timedelta(days=(product.weekday - valuation_day.weekday()) % 7)
    target = anchor if is_trading_day(anchor) else previous_trading_day(anchor)
    return target == valuation_day
