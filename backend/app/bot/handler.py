"""Telegram bot message handler with optional OpenAI NL understanding."""
from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import asyncpg

from app.bot.dates import fmt_date, fmt_period, now_moscow, parse_date_range
from app.config import settings

logger = logging.getLogger(__name__)
_MOSCOW = ZoneInfo(settings.timezone)


def _fmt_money(amount) -> str:
    """Format Decimal/float as money string."""
    return f"{Decimal(str(amount)):,.0f}".replace(',', ' ') + " ₽"


def _fmt_hours(h: float) -> str:
    if h == 0:
        return "0 ч"
    total_min = int(h * 60)
    hours, mins = divmod(total_min, 60)
    if mins == 0:
        return f"{hours} ч"
    return f"{hours} ч {mins} м"


def _contains(text: str, *words) -> bool:
    return any(w in text for w in words)


# ── OpenAI tool definitions ────────────────────────────────────────────────────

_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_today_stats",
            "description": "Показать сводку за сегодня: кто пришёл, опоздал, отсутствует",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_today_late",
            "description": "Кто опоздал сегодня",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_today_absent",
            "description": "Кто отсутствует / не вышел сегодня",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_attendance",
            "description": "Кто работал в указанный день или период",
            "parameters": {
                "type": "object",
                "properties": {
                    "period": {
                        "type": "string",
                        "description": (
                            "Период на русском: 'сегодня', 'вчера', 'эта неделя', "
                            "'прошлая неделя', 'этот месяц', 'прошлый месяц', "
                            "или конкретная дата/диапазон 'с 01.05 по 15.05'"
                        ),
                    }
                },
                "required": ["period"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_salary",
            "description": "Расчёт зарплаты сотрудников за период",
            "parameters": {
                "type": "object",
                "properties": {
                    "period": {
                        "type": "string",
                        "description": "Период на русском (как в get_attendance)",
                    },
                    "name": {
                        "type": "string",
                        "description": "Имя конкретного сотрудника (если нужен один)",
                    },
                },
                "required": ["period"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_revenue",
            "description": "Показать выручку за период",
            "parameters": {
                "type": "object",
                "properties": {
                    "period": {
                        "type": "string",
                        "description": "Период на русском (как в get_attendance)",
                    }
                },
                "required": ["period"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_schedule",
            "description": "Показать график / часы работы сотрудников за период",
            "parameters": {
                "type": "object",
                "properties": {
                    "period": {
                        "type": "string",
                        "description": "Период на русском (как в get_attendance)",
                    }
                },
                "required": ["period"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_employees",
            "description": "Список всех активных сотрудников с должностями и ставками",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "show_help",
            "description": "Показать справку — что умеет бот",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]


class BotHandler:
    def __init__(self, db: asyncpg.Pool):
        self.db = db

    async def handle(self, text: str) -> str:
        # Try OpenAI first if API key is configured
        if settings.openai_api_key:
            try:
                return await self._handle_openai(text)
            except Exception as exc:
                logger.warning("OpenAI handling failed, falling back to keywords: %s", exc)

        return await self._handle_keywords(text)

    # ── OpenAI path ───────────────────────────────────────────────────────────

    async def _handle_openai(self, text: str) -> str:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=settings.openai_api_key)

        today = now_moscow()
        system_prompt = (
            f"Ты — умный ассистент для кафе, отвечаешь на вопросы о посещаемости, "
            f"зарплате, выручке и расписании сотрудников. "
            f"Сегодня {today.strftime('%d.%m.%Y')} ({['понедельник','вторник','среда','четверг','пятница','суббота','воскресенье'][today.weekday()]}).\n"
            f"Используй функции чтобы получить нужные данные. "
            f"Для периодов всегда передавай строку на русском языке."
        )

        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ],
            tools=_TOOLS,
            tool_choice="auto",
            temperature=0,
        )

        msg = response.choices[0].message

        # No tool call — just text response
        if not msg.tool_calls:
            return msg.content or "🤔 Не понял вопрос. Напишите /help"

        # Execute all tool calls (usually just one)
        results = []
        for tc in msg.tool_calls:
            fn = tc.function.name
            try:
                args = json.loads(tc.function.arguments) if tc.function.arguments else {}
            except json.JSONDecodeError:
                args = {}

            result = await self._dispatch(fn, args)
            results.append(result)

        return "\n\n".join(results)

    async def _dispatch(self, fn: str, args: dict) -> str:
        """Route OpenAI function call to actual handler."""
        period = args.get("period", "сегодня")

        if fn == "get_today_stats":
            return await self._today_stats()
        elif fn == "get_today_late":
            return await self._today_late()
        elif fn == "get_today_absent":
            return await self._today_absent()
        elif fn == "get_attendance":
            d_from, d_to = parse_date_range(period)
            return await self._attendance_for_period(d_from, d_to)
        elif fn == "get_salary":
            d_from, d_to = parse_date_range(period)
            name = args.get("name")
            return await self._salary_report(d_from, d_to, name)
        elif fn == "get_revenue":
            d_from, d_to = parse_date_range(period)
            return await self._revenue_report(d_from, d_to)
        elif fn == "get_schedule":
            d_from, d_to = parse_date_range(period)
            return await self._schedule_report(d_from, d_to)
        elif fn == "get_employees":
            return await self._employees_list()
        elif fn == "show_help":
            return self._help()
        else:
            return "❌ Неизвестная команда."

    # ── Keyword fallback ──────────────────────────────────────────────────────

    async def _handle_keywords(self, text: str) -> str:
        t = text.lower().strip()

        # ── Help ──
        if t in ['/start', '/help', 'помощь', 'помоги', 'что умеешь']:
            return self._help()

        # ── Today: who is present / absent / late ──
        if _contains(t, 'кто сейчас', 'кто на месте', 'кто работает', 'кто пришёл', 'кто пришел',
                     'кто открыл', 'сводка сегодня', 'сводку') \
                or (t in ['сегодня', 'сводка']):
            return await self._today_stats()

        if _contains(t, 'кто опоздал', 'опоздан', 'опоздали'):
            return await self._today_late()

        if _contains(t, 'кто отсутству', 'кто не вышел', 'кто не пришёл', 'кто не пришел',
                     'кто дома', 'кто прогул'):
            return await self._today_absent()

        # ── Attendance for a date / period ──
        if _contains(t, 'кто работал', 'кто был', 'кто вышел', 'явка', 'посещаем'):
            d_from, d_to = parse_date_range(t)
            return await self._attendance_for_period(d_from, d_to)

        # ── Salary ──
        if _contains(t, 'зарплат', 'заработ', 'оклад', 'сколько зараб'):
            d_from, d_to = parse_date_range(t)
            name_filter = self._extract_name(t)
            return await self._salary_report(d_from, d_to, name_filter)

        # ── Revenue ──
        if _contains(t, 'выручк', 'выруч', 'доход', 'касс'):
            d_from, d_to = parse_date_range(t)
            return await self._revenue_report(d_from, d_to)

        # ── Schedule / hours ──
        if _contains(t, 'график', 'расписан', 'смен', 'часы', 'сколько часов'):
            d_from, d_to = parse_date_range(t)
            return await self._schedule_report(d_from, d_to)

        # ── Employees list ──
        if _contains(t, 'список сотрудников', 'сотрудники', 'кто у нас работает',
                     'персонал', 'все сотрудники'):
            return await self._employees_list()

        return (
            "🤔 Не понял вопрос. Напишите /help чтобы увидеть что я умею.\n\n"
            "Или задайте вопрос иначе, например:\n"
            "• <i>Кто сегодня на месте?</i>\n"
            "• <i>Выручка за эту неделю</i>\n"
            "• <i>Зарплата за этот месяц</i>"
        )

    # ── Today stats ───────────────────────────────────────────────────────────

    async def _today_stats(self) -> str:
        today = now_moscow()
        tz = _MOSCOW
        shift_minutes = settings.shift_start_hour * 60 + settings.late_threshold_minutes

        async with self.db.acquire() as conn:
            employees = await conn.fetch(
                "SELECT id, name FROM users WHERE is_active=TRUE AND role='employee' AND status='active' ORDER BY name"
            )
            checkins = await conn.fetch(
                """SELECT DISTINCT ON (user_id) user_id, timestamp
                   FROM attendance_logs
                   WHERE action='check_in' AND (timestamp AT TIME ZONE $1)::date = $2
                   ORDER BY user_id, timestamp ASC""",
                settings.timezone, today,
            )

        ci_map = {r['user_id']: r['timestamp'] for r in checkins}
        present, late, absent = [], [], []
        for emp in employees:
            uid, name = emp['id'], emp['name']
            if uid not in ci_map:
                absent.append(name)
            else:
                ts = ci_map[uid].astimezone(tz)
                mins = ts.hour * 60 + ts.minute
                time_str = ts.strftime('%H:%M')
                if mins > shift_minutes:
                    late.append(f"{name} ({time_str}, +{mins - shift_minutes} м)")
                else:
                    present.append(f"{name} ({time_str})")

        lines = [f"📊 <b>Сводка за {fmt_date(today)}</b>\n"]
        if present:
            lines.append(f"✅ <b>На месте ({len(present)}):</b>")
            lines.extend(f"  • {p}" for p in present)
        if late:
            lines.append(f"\n🕐 <b>Опоздали ({len(late)}):</b>")
            lines.extend(f"  • {p}" for p in late)
        if absent:
            lines.append(f"\n❌ <b>Отсутствуют ({len(absent)}):</b>")
            lines.extend(f"  • {p}" for p in absent)
        if not present and not late and not absent:
            lines.append("Нет активных сотрудников.")

        return "\n".join(lines)

    async def _today_late(self) -> str:
        today = now_moscow()
        tz = _MOSCOW
        shift_minutes = settings.shift_start_hour * 60 + settings.late_threshold_minutes

        async with self.db.acquire() as conn:
            employees = await conn.fetch(
                "SELECT id, name FROM users WHERE is_active=TRUE AND role='employee' AND status='active'"
            )
            checkins = await conn.fetch(
                """SELECT DISTINCT ON (user_id) user_id, timestamp
                   FROM attendance_logs WHERE action='check_in'
                   AND (timestamp AT TIME ZONE $1)::date = $2
                   ORDER BY user_id, timestamp ASC""",
                settings.timezone, today,
            )

        ci_map = {r['user_id']: r['timestamp'] for r in checkins}
        late = []
        for emp in employees:
            uid, name = emp['id'], emp['name']
            if uid in ci_map:
                ts = ci_map[uid].astimezone(tz)
                mins = ts.hour * 60 + ts.minute
                if mins > shift_minutes:
                    late.append(f"{name} — {ts.strftime('%H:%M')} (+{mins - shift_minutes} мин)")

        if not late:
            return "🎉 Опозданий сегодня нет!"
        return f"🕐 <b>Опоздали сегодня ({len(late)}):</b>\n" + "\n".join(f"  • {l}" for l in late)

    async def _today_absent(self) -> str:
        today = now_moscow()
        async with self.db.acquire() as conn:
            employees = await conn.fetch(
                "SELECT id, name FROM users WHERE is_active=TRUE AND role='employee' AND status='active' ORDER BY name"
            )
            present_ids = await conn.fetch(
                """SELECT DISTINCT user_id FROM attendance_logs
                   WHERE action='check_in' AND (timestamp AT TIME ZONE $1)::date = $2""",
                settings.timezone, today,
            )
        present_set = {r['user_id'] for r in present_ids}
        absent = [emp['name'] for emp in employees if emp['id'] not in present_set]
        if not absent:
            return "✅ Все сотрудники сегодня вышли!"
        return f"❌ <b>Отсутствуют сегодня ({len(absent)}):</b>\n" + "\n".join(f"  • {a}" for a in absent)

    # ── Attendance for period ─────────────────────────────────────────────────

    async def _attendance_for_period(self, d_from: date, d_to: date) -> str:
        async with self.db.acquire() as conn:
            logs = await conn.fetch(
                """SELECT DISTINCT u.name,
                          (timestamp AT TIME ZONE $1)::date AS work_date
                   FROM attendance_logs al
                   JOIN users u ON u.id = al.user_id
                   WHERE al.action = 'check_in'
                     AND (timestamp AT TIME ZONE $1)::date >= $2
                     AND (timestamp AT TIME ZONE $1)::date <= $3
                   ORDER BY work_date, u.name""",
                settings.timezone, d_from, d_to,
            )

        if not logs:
            return f"📭 Нет данных за {fmt_period(d_from, d_to)}"

        if d_from == d_to:
            names = [r['name'] for r in logs]
            return (
                f"👥 <b>Работали {fmt_date(d_from)} ({len(names)}):</b>\n"
                + "\n".join(f"  • {n}" for n in names)
            )

        # Group by date
        by_date: dict[date, list[str]] = {}
        for r in logs:
            by_date.setdefault(r['work_date'], []).append(r['name'])

        lines = [f"📅 <b>Явка за {fmt_period(d_from, d_to)}:</b>"]
        for d in sorted(by_date):
            dow = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'][d.weekday()]
            names = ", ".join(by_date[d])
            lines.append(f"  <b>{dow} {fmt_date(d)}:</b> {names}")
        return "\n".join(lines)

    # ── Salary ────────────────────────────────────────────────────────────────

    async def _salary_report(self, d_from: date, d_to: date, name_filter: str | None) -> str:
        async with self.db.acquire() as conn:
            if name_filter:
                employees = await conn.fetch(
                    """SELECT id, name, hourly_rate, bonus_percent FROM users
                       WHERE is_active=TRUE AND status='active' AND role='employee'
                       AND LOWER(name) LIKE $1 ORDER BY name""",
                    f"%{name_filter.lower()}%",
                )
            else:
                employees = await conn.fetch(
                    """SELECT id, name, hourly_rate, bonus_percent FROM users
                       WHERE is_active=TRUE AND status='active' AND role='employee' ORDER BY name"""
                )
            logs = await conn.fetch(
                """SELECT user_id, action, timestamp FROM attendance_logs
                   WHERE timestamp >= $1::date AND timestamp < ($2::date + INTERVAL '1 day')
                   AND action IN ('check_in','check_out') ORDER BY user_id, timestamp""",
                d_from, d_to,
            )
            rev = await conn.fetchval(
                "SELECT COALESCE(SUM(amount),0) FROM revenue_entries WHERE date >= $1 AND date <= $2",
                d_from, d_to,
            )

        total_rev = Decimal(str(rev))

        def calc_hours(uid):
            evs = [l for l in logs if l['user_id'] == uid]
            total_sec = 0.0
            last_in = None
            for ev in sorted(evs, key=lambda e: e['timestamp']):
                if ev['action'] == 'check_in':
                    last_in = ev['timestamp']
                elif ev['action'] == 'check_out' and last_in:
                    total_sec += (ev['timestamp'] - last_in).total_seconds()
                    last_in = None
            return round(total_sec / 3600, 2)

        if not employees:
            return "Сотрудники не найдены."

        lines = [f"💰 <b>Зарплата за {fmt_period(d_from, d_to)}</b>"]
        if total_rev > 0:
            lines.append(f"Выручка: {_fmt_money(total_rev)}\n")

        grand_total = Decimal('0')
        for emp in employees:
            hours = calc_hours(emp['id'])
            rate = Decimal(str(emp['hourly_rate']))
            pct = Decimal(str(emp['bonus_percent']))
            base = (Decimal(str(hours)) * rate).quantize(Decimal('0.01'))
            bonus = (total_rev * pct / 100).quantize(Decimal('0.01'))
            total = base + bonus
            grand_total += total
            lines.append(
                f"👤 <b>{emp['name']}</b>\n"
                f"   Часы: {_fmt_hours(hours)} × {rate} ₽ = {_fmt_money(base)}"
                + (f"\n   Бонус: {_fmt_money(bonus)}" if bonus > 0 else "")
                + f"\n   <b>Итого: {_fmt_money(total)}</b>"
            )

        if len(employees) > 1:
            lines.append(f"\n💼 <b>Всего к выплате: {_fmt_money(grand_total)}</b>")

        return "\n".join(lines)

    def _extract_name(self, text: str) -> str | None:
        """Try to find a name in the text (simplified: disabled for now)."""
        return None

    # ── Revenue ───────────────────────────────────────────────────────────────

    async def _revenue_report(self, d_from: date, d_to: date) -> str:
        async with self.db.acquire() as conn:
            rows = await conn.fetch(
                """SELECT date, amount, note FROM revenue_entries
                   WHERE date >= $1 AND date <= $2 ORDER BY date""",
                d_from, d_to,
            )
            total = await conn.fetchval(
                "SELECT COALESCE(SUM(amount),0) FROM revenue_entries WHERE date >= $1 AND date <= $2",
                d_from, d_to,
            )

        if not rows:
            return f"📭 Выручка за {fmt_period(d_from, d_to)} не внесена."

        if d_from == d_to:
            r = rows[0]
            note = f"\nПримечание: {r['note']}" if r['note'] else ""
            return f"📈 <b>Выручка за {fmt_date(d_from)}:</b> {_fmt_money(r['amount'])}{note}"

        lines = [f"📈 <b>Выручка за {fmt_period(d_from, d_to)}:</b>"]
        for r in rows:
            dow = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'][r['date'].weekday()]
            note = f" ({r['note']})" if r['note'] else ""
            lines.append(f"  {dow} {fmt_date(r['date'])}: {_fmt_money(r['amount'])}{note}")
        lines.append(f"\n💼 <b>Итого: {_fmt_money(total)}</b>")
        return "\n".join(lines)

    # ── Schedule ──────────────────────────────────────────────────────────────

    async def _schedule_report(self, d_from: date, d_to: date) -> str:
        tz = _MOSCOW
        async with self.db.acquire() as conn:
            employees = await conn.fetch(
                "SELECT id, name FROM users WHERE is_active=TRUE AND role='employee' AND status='active' ORDER BY name"
            )
            logs = await conn.fetch(
                """SELECT user_id, action, timestamp FROM attendance_logs
                   WHERE (timestamp AT TIME ZONE $1)::date >= $2
                     AND (timestamp AT TIME ZONE $1)::date <= $3
                     AND action IN ('check_in','check_out')
                   ORDER BY user_id, timestamp""",
                settings.timezone, d_from, d_to,
            )

        user_logs: dict[int, list] = defaultdict(list)
        for log in logs:
            user_logs[log['user_id']].append(log)

        def calc_day(uid, d):
            day_logs = [l for l in user_logs[uid]
                        if l['timestamp'].astimezone(tz).date() == d]
            day_logs.sort(key=lambda x: x['timestamp'])
            ci = co = None
            last_in = None
            total_sec = 0.0
            for ev in day_logs:
                ts = ev['timestamp'].astimezone(tz)
                if ev['action'] == 'check_in':
                    if ci is None:
                        ci = ts.strftime('%H:%M')
                    last_in = ev['timestamp']
                elif ev['action'] == 'check_out' and last_in:
                    co = ts.strftime('%H:%M')
                    total_sec += (ev['timestamp'] - last_in).total_seconds()
                    last_in = None
            hours = round(total_sec / 3600, 1)
            return ci, co, hours

        if d_from == d_to:
            lines = [f"📅 <b>График за {fmt_date(d_from)}:</b>"]
            total_emp = 0
            for emp in employees:
                ci, co, h = calc_day(emp['id'], d_from)
                if ci:
                    co_str = co if co else "ещё на месте"
                    h_str = f" ({_fmt_hours(h)})" if h > 0 else ""
                    lines.append(f"  • {emp['name']}: {ci} — {co_str}{h_str}")
                    total_emp += 1
            if total_emp == 0:
                lines.append("  Никто не работал.")
            return "\n".join(lines)

        # Multi-day: summarize total hours per employee
        lines = [f"📅 <b>График за {fmt_period(d_from, d_to)}:</b>"]
        dates = [d_from + timedelta(days=i) for i in range((d_to - d_from).days + 1)]
        for emp in employees:
            total_h = 0.0
            days_worked = 0
            for d in dates:
                ci, co, h = calc_day(emp['id'], d)
                if ci:
                    days_worked += 1
                    total_h += h
            if days_worked > 0:
                lines.append(f"  • {emp['name']}: {days_worked} дн, {_fmt_hours(total_h)}")
        if len(lines) == 1:
            lines.append("  Нет данных.")
        return "\n".join(lines)

    # ── Employee list ─────────────────────────────────────────────────────────

    async def _employees_list(self) -> str:
        async with self.db.acquire() as conn:
            rows = await conn.fetch(
                "SELECT name, position, hourly_rate FROM users WHERE is_active=TRUE AND role='employee' AND status='active' ORDER BY name"
            )
        if not rows:
            return "Нет активных сотрудников."
        POSITIONS = {
            'runner': 'Ранер', 'cook': 'Повар', 'barman': 'Бармен',
            'admin': 'Админ', 'employee': 'Сотрудник',
        }
        lines = [f"👥 <b>Сотрудники ({len(rows)}):</b>"]
        for r in rows:
            pos = POSITIONS.get(r['position'], r['position'])
            lines.append(f"  • {r['name']} — {pos}, {r['hourly_rate']} ₽/ч")
        return "\n".join(lines)

    # ── Help ─────────────────────────────────────────────────────────────────

    def _help(self) -> str:
        return (
            "🤖 <b>Бот учёта рабочего времени</b>\n\n"
            "Задавайте вопросы в свободной форме:\n\n"
            "📊 <b>Кто сегодня работает?</b>\n"
            "   → сводка: кто пришёл, опоздал, отсутствует\n\n"
            "📅 <b>Кто работал 15.05?</b>\n"
            "   → явка за конкретный день или период\n\n"
            "💰 <b>Зарплата за этот месяц</b>\n"
            "   → расчёт зарплат за период\n\n"
            "📈 <b>Выручка за эту неделю</b>\n"
            "   → сумма выручки за период\n\n"
            "🗓 <b>График за прошлую неделю</b>\n"
            "   → кто сколько часов отработал\n\n"
            "👥 <b>Список сотрудников</b>\n"
            "   → все активные сотрудники\n\n"
            "<i>Понимаю: сегодня, вчера, эту/прошлую неделю, "
            "этот/прошлый месяц, конкретные даты (ДД.ММ или с ДД.ММ по ДД.ММ)</i>"
        )
