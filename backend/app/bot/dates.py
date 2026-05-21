"""Parse Russian date expressions from natural language text."""
from __future__ import annotations

import re
from datetime import date, timedelta
from zoneinfo import ZoneInfo
from app.config import settings


def now_moscow() -> date:
    from datetime import datetime
    return datetime.now(ZoneInfo(settings.timezone)).date()


def parse_date_range(text: str) -> tuple[date, date]:
    """
    Extract date range from Russian text.
    Returns (date_from, date_to).
    Defaults: today if no date found.
    """
    today = now_moscow()
    text = text.lower()

    # "с DD.MM[.YYYY] по DD.MM[.YYYY]"
    m = re.search(r'с\s+(\d{1,2})[./](\d{1,2})(?:[./](\d{2,4}))?\s+по\s+(\d{1,2})[./](\d{1,2})(?:[./](\d{2,4}))?', text)
    if m:
        y1 = int(m.group(3)) if m.group(3) else today.year
        if y1 < 100: y1 += 2000
        y2 = int(m.group(6)) if m.group(6) else today.year
        if y2 < 100: y2 += 2000
        try:
            return date(y1, int(m.group(2)), int(m.group(1))), date(y2, int(m.group(5)), int(m.group(4)))
        except ValueError:
            pass

    # "за DD.MM[.YYYY]" or just "DD.MM[.YYYY]"
    m = re.search(r'(\d{1,2})[./](\d{1,2})(?:[./](\d{2,4}))?', text)
    if m:
        y = int(m.group(3)) if m.group(3) else today.year
        if y < 100: y += 2000
        try:
            d = date(y, int(m.group(2)), int(m.group(1)))
            return d, d
        except ValueError:
            pass

    # Named periods
    if any(w in text for w in ['вчера', 'вчерашн']):
        d = today - timedelta(days=1)
        return d, d
    if any(w in text for w in ['эту неделю', 'этой недели', 'текущ', 'эта неделя', 'эту нед']):
        mon = today - timedelta(days=today.weekday())
        return mon, mon + timedelta(days=6)
    if any(w in text for w in ['прошлую неделю', 'прошлой недели', 'прошлой нед', 'прошедш']):
        mon = today - timedelta(days=today.weekday() + 7)
        return mon, mon + timedelta(days=6)
    if any(w in text for w in ['этот месяц', 'этого месяца', 'текущий месяц', 'этом месяц']):
        return today.replace(day=1), today
    if any(w in text for w in ['прошлый месяц', 'прошлого месяца', 'прошлом месяц']):
        first_this = today.replace(day=1)
        last_prev = first_this - timedelta(days=1)
        return last_prev.replace(day=1), last_prev
    if any(w in text for w in ['сегодня', 'сейчас', 'сегодн']):
        return today, today

    # Default: today
    return today, today


def fmt_date(d: date) -> str:
    return d.strftime('%d.%m.%Y')


def fmt_period(d1: date, d2: date) -> str:
    if d1 == d2:
        return fmt_date(d1)
    return f"{fmt_date(d1)} — {fmt_date(d2)}"
