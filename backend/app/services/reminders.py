"""Eslatma dvigateli.

Qoida: **muddat qanchalik yaqin bo'lsa, eslatma shuncha tez-tez boradi.**

    muddatgacha 4+ kun   -> kuniga 1   (09:00)
    muddatgacha 1-3 kun  -> kuniga 2   (09:00, 17:00)
    bugun tugaydi        -> kuniga 3   (09:00, 13:00, muddatdan 2 soat oldin)
    muddat o'tdi         -> kuniga 3   (09:00, 13:00, 17:00)

Boss va assistantga alohida: muddatdan **+1 soat** o'tganda darhol bitta xabar, va har kuni
ertalab kechikkanlar ro'yxati. Vazifa topshirilgan zahoti eslatma to'xtaydi.

Tunda tinchlik: 21:00 - 08:00 orasida hech narsa yuborilmaydi. O'sha vaqtga to'g'ri kelgani
yo'qolmaydi — ertalab birinchi ishga tushishda yuboriladi, chunki takrorlanmaslik `dedupe_key`
bilan ta'minlangan, "yuborildimi" degan holat kodda saqlanmaydi.

Scheduler buni har 5 daqiqada chaqiradi; funksiya idempotent — bir necha marta chaqirilsa ham
bitta xabar yoziladi.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import clock
from ..models import NEW, PROGRESS, AppSetting, Task, User
from .tasks import managers, notify, task_payload

QUIET_FROM = 21   # 21:00 dan keyin yuborilmaydi
QUIET_TO = 8      # 08:00 gacha yuborilmaydi
DEFAULT_HOURS = (9, 13, 17)
LATE_ALERT_AFTER = timedelta(hours=1)   # boss/assistantga "kechikdi" xabari shu vaqtdan keyin


def reminder_hours(db: Session) -> tuple[int, ...]:
    """Sozlamadan o'qiladi (`app_settings.reminder_hours` = "9,13,17"), kodga tegmasdan
    o'zgartirish uchun. Noto'g'ri qiymat kiritilsa standartga qaytadi."""
    row = db.get(AppSetting, "reminder_hours")
    try:
        hours = tuple(sorted({int(x) for x in (row.value or "").split(",") if x.strip() != ""}))
    except (AttributeError, ValueError):
        return DEFAULT_HOURS
    hours = tuple(h for h in hours if 0 <= h <= 23)
    return hours or DEFAULT_HOURS


def is_quiet(at: datetime) -> bool:
    return at.hour >= QUIET_FROM or at.hour < QUIET_TO


def slots_for(task: Task, ref: datetime, hours: tuple[int, ...] = DEFAULT_HOURS) -> list[datetime]:
    """Shu kuni ijrochiga qaysi soatlarda eslatma borishi kerak. Faqat `ref` dan oldingi
    (ya'ni vaqti kelgan) va tunga to'g'ri kelmaganlari qaytadi."""
    today = ref.date()
    days_left = (task.due_at.date() - today).days
    if days_left >= 4:
        times = [clock.at(today, hours[0])]
    elif days_left >= 1:
        times = [clock.at(today, hours[0]), clock.at(today, hours[-1])]
    elif days_left == 0:
        times = [clock.at(today, h) for h in hours[:-1]] + [task.due_at - timedelta(hours=2)]
    else:
        times = [clock.at(today, h) for h in hours]
    out = []
    for t in times:
        if t > ref or is_quiet(t):
            continue
        # bugun tugaydigan vazifada "muddatdan 2 soat oldin" allaqachon o'tgan soatlar bilan
        # ustma-ust tushmasin
        if any(abs((t - o).total_seconds()) < 1800 for o in out):
            continue
        out.append(t)
    return sorted(out)


def _key(prefix: str, *parts) -> str:
    return ":".join([prefix, *(str(p) for p in parts)])


def run_reminders(db: Session, ref: datetime | None = None) -> dict:
    """Vaqti kelgan eslatmalarni navbatga qo'yadi. Nechta yozilganini qaytaradi."""
    ref = ref or clock.now()
    made = {"assignee": 0, "late_alert": 0, "digest": 0}
    if is_quiet(ref):
        return made

    hours = reminder_hours(db)
    open_tasks = db.scalars(
        select(Task).where(Task.status.in_((NEW, PROGRESS))).order_by(Task.due_at)).all()
    if not open_tasks:
        return made

    people = {u.id: u for u in db.scalars(select(User).where(User.is_active.is_(True)))}
    late_tasks: list[Task] = []

    for t in open_tasks:
        overdue = t.due_at < ref
        if overdue:
            late_tasks.append(t)

        # --- ijrochiga eslatma ---
        who = people.get(t.assignee_id)
        if who and who.telegram_user_id:
            for slot in slots_for(t, ref, hours):
                payload = task_payload(db, t, slot=slot.strftime("%H:%M"), overdue=overdue)
                if notify(db, t.assignee_id, "reminder", t, payload,
                          dedupe_key=_key("rem", t.id, slot.strftime("%Y%m%d%H%M"))):
                    made["assignee"] += 1

        # --- boss va assistantga: muddatdan +1 soat o'tdi ---
        if overdue and ref - t.due_at >= LATE_ALERT_AFTER:
            payload = task_payload(db, t)
            for m in managers(db):
                if notify(db, m.id, "overdue_alert", t, payload, dedupe_key=_key("late1h", t.id, m.id)):
                    made["late_alert"] += 1

    # --- boss va assistantga: kunlik kechikkanlar ro'yxati ---
    if late_tasks and ref.hour >= hours[0]:
        today = ref.date()
        items = [{"code": t.code, "title": t.title,
                  "assignee_name": people[t.assignee_id].full_name if t.assignee_id in people else "—",
                  "late_days": max(0, int((ref - t.due_at).total_seconds()) // 86400)}
                 for t in late_tasks[:20]]
        payload = {"count": len(late_tasks), "items": items, "date": today.isoformat()}
        for m in managers(db):
            if notify(db, m.id, "overdue_digest", None, payload, dedupe_key=_key("digest", m.id, today)):
                made["digest"] += 1

    db.commit()
    return made


def due_today_digest(db: Session, ref: datetime | None = None) -> int:
    """Ertalabki xulosa: bugun tugaydigan vazifalar boss va assistantga."""
    ref = ref or clock.now()
    today: date = ref.date()
    start, end = clock.at(today, 0, 0), clock.at(today, 23, 59)
    rows = db.scalars(select(Task).where(
        Task.status.in_((NEW, PROGRESS)), Task.due_at >= start, Task.due_at <= end)).all()
    if not rows:
        return 0
    names = {u.id: u.full_name for u in db.scalars(select(User))}
    payload = {"count": len(rows), "date": today.isoformat(),
               "items": [{"code": t.code, "title": t.title,
                          "assignee_name": names.get(t.assignee_id, "—"),
                          "due_at": t.due_at.isoformat(timespec="minutes")} for t in rows[:20]]}
    n = 0
    for m in managers(db):
        if notify(db, m.id, "due_today", None, payload, dedupe_key=_key("today", m.id, today)):
            n += 1
    db.commit()
    return n
