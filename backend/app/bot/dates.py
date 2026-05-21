"""Parse Russian date expressions from natural language text."""
from __future__ import annotations

import calendar
import re
from datetime import date, timedelta
from zoneinfo import ZoneInfo
from app.config import settings


def now_moscow() -> date:
    from datetime import datetime
    return datetime.now(ZoneInfo(settings.timezone)).date()


# ── Month name lookup ─────────────────────────────────────────────────────────

_MONTHS: dict[str, int] = {
    # nominative
    "январь": 1, "февраль": 2, "март": 3, "апрель": 4,
    "май": 5, "июнь": 6, "июль": 7, "август": 8,
    "сентябрь": 9, "октябрь": 10, "ноябрь": 11, "декабрь": 12,
    # genitive / prepositional
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4,
    "мая": 5, "июня": 6, "июля": 7, "августа": 8,
    "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,
    # prepositional
    "январе": 1, "феврале": 2, "марте": 3, "апреле": 4,
    "мае": 5, "июне": 6, "июле": 7, "августе": 8,
    "сентябре": 9, "октябре": 10, "ноябре": 11, "декабре": 12,
}

_MONTH_PATTERN = re.compile(
    r"\b(" + "|".join(sorted(_MONTHS, key=len, reverse=True)) + r")\b"
)


def _month_range(month: int, year: int) -> tuple[date, date]:
    """Return (first_day, last_day) of the given month/year."""
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)


def parse_date_range(text: str) -> tuple[date, date]:
    """
    Extract date range from Russian text.
    Returns (date_from, date_to).
    Defaults to today if no date found.
    """
    today = now_moscow()
    t = text.lower()

    # ── "с DD.MM[.YYYY] по DD.MM[.YYYY]" ────────────────────────────────────
    m = re.search(
        r'с\s+(\d{1,2})[./](\d{1,2})(?:[./](\d{2,4}))?\s+по\s+(\d{1,2})[./](\d{1,2})(?:[./](\d{2,4}))?',
        t,
    )
    if m:
        y1 = int(m.group(3)) if m.group(3) else today.year
        if y1 < 100: y1 += 2000
        y2 = int(m.group(6)) if m.group(6) else today.year
        if y2 < 100: y2 += 2000
        try:
            return date(y1, int(m.group(2)), int(m.group(1))), date(y2, int(m.group(5)), int(m.group(4)))
        except ValueError:
            pass

    # ── "за DD.MM[.YYYY]" or just "DD.MM[.YYYY]" ────────────────────────────
    m = re.search(r'(\d{1,2})[./](\d{1,2})(?:[./](\d{2,4}))?', t)
    if m:
        y = int(m.group(3)) if m.group(3) else today.year
        if y < 100: y += 2000
        try:
            d = date(y, int(m.group(2)), int(m.group(1)))
            return d, d
        except ValueError:
            pass

    # ── Named periods ────────────────────────────────────────────────────────

    if any(w in t for w in ['вчера', 'вчерашн']):
        d = today - timedelta(days=1)
        return d, d

    if any(w in t for w in ['эту неделю', 'этой недели', 'текущ', 'эта неделя',
                              'эту нед', 'на этой нед', 'текущая неделя']):
        mon = today - timedelta(days=today.weekday())
        return mon, mon + timedelta(days=6)

    if any(w in t for w in ['прошлую неделю', 'прошлой недели', 'прошлой нед',
                              'прошедш', 'прошлая неделя']):
        mon = today - timedelta(days=today.weekday() + 7)
        return mon, mon + timedelta(days=6)

    if any(w in t for w in ['этот месяц', 'этого месяца', 'текущий месяц',
                              'этом месяц', 'текущего месяца']):
        return today.replace(day=1), today

    if any(w in t for w in ['прошлый месяц', 'прошлого месяца', 'прошлом месяц',
                              'прошлый мес', 'за прошлый']):
        first_this = today.replace(day=1)
        last_prev = first_this - timedelta(days=1)
        return last_prev.replace(day=1), last_prev

    if any(w in t for w in ['сегодня', 'сейчас', 'сегодн']):
        return today, today

    # ── Month name: "за апрель", "в апреле", "апрель 2025" etc. ─────────────
    m_name = _MONTH_PATTERN.search(t)
    if m_name:
        month_num = _MONTHS[m_name.group(1)]
        # Look for explicit 4-digit year right after the month name
        year_m = re.search(r'\b(20\d{2})\b', t)
        if year_m:
            year = int(year_m.group(1))
        else:
            # If the named month is in the future this year, assume last year
            year = today.year
            if month_num > today.month:
                year -= 1
        return _month_range(month_num, year)

    # ── Default: today ────────────────────────────────────────────────────────
    return today, today


def fmt_date(d: date) -> str:
    return d.strftime('%d.%m.%Y')


def fmt_period(d1: date, d2: date) -> str:
    if d1 == d2:
        return fmt_date(d1)
    return f"{fmt_date(d1)} — {fmt_date(d2)}"
