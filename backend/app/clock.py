"""Vaqt bitta joydan olinadi.

Qoida: **domen vaqti mahalliy** (Asia/Tashkent, naive), **xavfsizlik vaqti UTC**.
Sabab: muddat, eslatma soatlari va hisobot davrlari odamning soatiga qarab ishlaydi —
"ertaga 18:00" Toshkentdagi 18:00. JWT va refresh token esa UTC'da qoladi, chunki ular
standart bo'yicha shunday tekshiriladi. Ikkalasini aralashtirmaslik uchun domen kodi
faqat shu modulni chaqiradi, `datetime.utcnow()` ni emas.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from .config import settings

_DEFAULT_HOUR = 18  # muddat soati ko'rsatilmasa - kun oxiri deb 18:00 olinadi


def tz() -> ZoneInfo:
    try:
        return ZoneInfo(settings.TZ_NAME)
    except Exception:  # noqa: BLE001 - noto'g'ri TZ_NAME server ko'tarilishiga to'sqinlik qilmasin
        return ZoneInfo("UTC")


def now() -> datetime:
    """Mahalliy vaqt, naive (bazada shu ko'rinishda saqlanadi)."""
    return datetime.now(tz()).replace(tzinfo=None)


def today() -> date:
    return now().date()


def at(d: date, hour: int = _DEFAULT_HOUR, minute: int = 0) -> datetime:
    return datetime.combine(d, time(hour, minute))


def end_of_day(d: date) -> datetime:
    return at(d, _DEFAULT_HOUR)


def parse_due(value) -> datetime | None:
    """`due_at` ni qabul qiladi: datetime, "2026-09-10T14:00", yoki "2026-09-10" (-> 18:00)."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None, microsecond=0)
    if isinstance(value, date):
        return end_of_day(value)
    s = str(value).strip().replace("Z", "")
    try:
        if len(s) == 10:
            return end_of_day(date.fromisoformat(s))
        return datetime.fromisoformat(s).replace(tzinfo=None, microsecond=0)
    except ValueError:
        return None


def days_between(a: date, b: date) -> int:
    return (a - b).days


def period_range(period: str, ref: date | None = None) -> tuple[date, date]:
    """'week' | 'month' | 'year' -> (boshi, oxiri) - ikkalasi ham kiradi."""
    d = ref or today()
    if period == "week":
        start = d - timedelta(days=d.weekday())
        return start, start + timedelta(days=6)
    if period == "year":
        return date(d.year, 1, 1), date(d.year, 12, 31)
    start = date(d.year, d.month, 1)
    nxt = date(d.year + 1, 1, 1) if d.month == 12 else date(d.year, d.month + 1, 1)
    return start, nxt - timedelta(days=1)
