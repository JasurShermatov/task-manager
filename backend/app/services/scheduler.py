"""Vaqt bo'yicha ishlar. API jarayoni ichida (APScheduler), soat mintaqasi settings.TZ_NAME.

Ikkita ish bor, ikkalasi ham idempotent — takrorlanishdan `Notification.dedupe_key` saqlaydi,
shuning uchun qayta ishga tushirish yoki bir necha marta chaqirish xavfsiz.
"""
from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler

from ..db import SessionLocal
from .reminders import due_today_digest, reminder_hours, run_reminders

log = logging.getLogger("scheduler")


def tick():
    """Har 5 daqiqada: vaqti kelgan eslatmalarni navbatga qo'yadi."""
    db = SessionLocal()
    try:
        made = run_reminders(db)
        if any(made.values()):
            log.info("eslatma: %s", made)
    except Exception:  # noqa: BLE001 - bitta xato keyingi ishni to'xtatmasin
        log.exception("run_reminders")
    finally:
        db.close()


def morning():
    """Ertalab: boss va assistantga bugun tugaydigan vazifalar ro'yxati."""
    db = SessionLocal()
    try:
        n = due_today_digest(db)
        if n:
            log.info("ertalabki xulosa: %d ta", n)
    except Exception:  # noqa: BLE001
        log.exception("due_today_digest")
    finally:
        db.close()


def start_scheduler(tz: str) -> BackgroundScheduler:
    db = SessionLocal()
    try:
        first_hour = reminder_hours(db)[0]
    finally:
        db.close()
    s = BackgroundScheduler(timezone=tz)
    s.add_job(tick, "interval", minutes=5, id="reminders", max_instances=1, coalesce=True)
    s.add_job(morning, "cron", hour=first_hour, minute=1, id="morning", max_instances=1, coalesce=True)
    s.start()
    log.info("scheduler ishga tushdi (%s), ertalabki xulosa %02d:01 da", tz, first_hour)
    return s
