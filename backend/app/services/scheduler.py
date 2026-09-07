"""Time-based jobs: reminders, review escalation, morning digest, recurring tasks.
Runs inside the API process (APScheduler). Times are Asia/Tashkent per settings.TZ_NAME.
Digest/reminder notifications are created once per day per (user, event, task) — guarded by a Redis key."""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from sqlalchemy import select, and_
from sqlalchemy.orm import Session

from ..db import SessionLocal
from ..models import Task, User, TaskRecurringRule, TaskTemplate, Location, Notification, Role
from ..redis_client import rds
from . import tasks as svc

log = logging.getLogger("scheduler")


def _once(key: str, ttl: int = 36 * 3600) -> bool:
    """True if this key was not yet used today."""
    k = f"sched:{date.today().isoformat()}:{key}"
    if rds.get(k):
        return False
    rds.set(k, "1", ex=ttl)
    return True


def _open_tasks(db: Session):
    return db.scalars(select(Task).where(Task.is_active == True, Task.status.in_(("plan", "progress", "review", "blocked")))).all()  # noqa


def morning_jobs():
    """08:00 — due tomorrow, overdue, overdue>3d to rahbar, block>24h, review 2/4/6 days, digest."""
    db = SessionLocal()
    try:
        today = date.today()
        now = datetime.utcnow()
        tasks = _open_tasks(db)
        rahbars = [u for u in db.scalars(select(User).join(Role).where(Role.code.in_(("rahbar",)), User.is_active == True))]  # noqa
        for t in tasks:
            if t.status in ("plan", "progress", "blocked"):
                if t.planned_end == today + timedelta(days=1) and _once(f"due_tomorrow:{t.id}"):
                    svc.notify(db, [t.assignee_id], "due_tomorrow", t, {"planned_end": str(t.planned_end)}, inapp=False)
                if t.planned_end < today:
                    days = (today - t.planned_end).days
                    if _once(f"overdue:{t.id}"):
                        svc.notify(db, {t.assignee_id} | svc.prorab_and_rahbar_ids(db, t) - {r.id for r in rahbars}, "overdue", t,
                                   {"days": days, "planned_end": str(t.planned_end)}, inapp=False)
                    if days > 3 and _once(f"overdue3:{t.id}"):
                        ids = [r.id for r in rahbars if r.scope_type == "system" or (r.scope_type == "project" and r.scope_id == t.project_id)]
                        svc.notify(db, ids, "overdue_3", t, {"days": days}, inapp=False)
            if t.status == "blocked" and t.blocked_at and (now - t.blocked_at) > timedelta(hours=24) and _once(f"block24:{t.id}"):
                ids = [r.id for r in rahbars if r.scope_type == "system" or (r.scope_type == "project" and r.scope_id == t.project_id)]
                svc.notify(db, ids, "blocked_24h", t, {"reason": t.blocked_reason, "days": (now - t.blocked_at).days}, inapp=False)
            if t.status == "review" and t.review_started_at:
                age = (now - t.review_started_at).days
                ids = [r.id for r in rahbars if r.scope_type == "system" or (r.scope_type == "project" and r.scope_id == t.project_id)]
                if age >= 2 and _once(f"review2:{t.id}"):
                    svc.notify(db, [t.reviewer_id], "review_aging", t, {"days": age}, inapp=False)
                if age >= 4 and _once(f"review4:{t.id}"):
                    svc.notify(db, [t.reviewer_id] + ids, "review_aging", t, {"days": age}, inapp=False)
                if age >= 6 and _once(f"review6:{t.id}"):
                    svc.notify(db, ids, "review_aging", t, {"days": age}, inapp=False)
        # digest per linked user
        users = db.scalars(select(User).where(User.is_active == True, User.telegram_user_id.isnot(None))).all()  # noqa
        for u in users:
            if not _once(f"digest:{u.id}"):
                continue
            mine = [t for t in tasks if t.assignee_id == u.id]
            today_due = [t for t in mine if t.planned_end == today and t.status != "review"]
            overdue = [t for t in mine if t.planned_end < today and t.status != "review"]
            blocked = [t for t in mine if t.status == "blocked"]
            in_review = [t for t in mine if t.status == "review"]
            queue = [t for t in tasks if t.reviewer_id == u.id and t.status == "review"]
            urgent = sorted([t for t in mine if t.status != "review"], key=lambda t: (t.planned_end, {"high": 0, "normal": 1, "low": 2}[t.priority]))[:3]
            role = u.role.code
            if role in ("rahbar", "admin", "kuzatuvchi") and u.scope_type in ("system", "project"):
                scope_tasks = [t for t in tasks if u.scope_type == "system" or t.project_id == u.scope_id]
                overdue = [t for t in scope_tasks if t.planned_end < today]
                blocked = [t for t in scope_tasks if t.status == "blocked"]
                in_review = [t for t in scope_tasks if t.status == "review"]
                today_due = [t for t in scope_tasks if t.planned_end == today]
            payload = {
                "today": [{"code": t.code, "title": t.title} for t in today_due[:10]],
                "overdue": [{"code": t.code, "title": t.title, "days": (today - t.planned_end).days} for t in overdue[:10]],
                "blocked": [{"code": t.code, "title": t.title, "reason": t.blocked_reason} for t in blocked[:10]],
                "review": [{"code": t.code, "title": t.title} for t in in_review[:10]],
                "urgent": [{"code": t.code, "title": t.title, "planned_end": str(t.planned_end)} for t in urgent],
                "queue_count": len(queue),
                "queue_oldest_days": max(((now - t.review_started_at).days for t in queue if t.review_started_at), default=0),
                "counts": {"today": len(today_due), "overdue": len(overdue), "blocked": len(blocked), "review": len(in_review)},
            }
            if any(payload["counts"].values()) or queue:
                svc.notify(db, [u.id], "digest", None, payload, inapp=False)
        db.commit()
    except Exception:
        log.exception("morning_jobs failed")
        db.rollback()
    finally:
        db.close()


def noon_jobs():
    """12:00 — due today."""
    db = SessionLocal()
    try:
        today = date.today()
        for t in _open_tasks(db):
            if t.planned_end == today and t.status in ("plan", "progress", "blocked") and _once(f"due_today:{t.id}"):
                svc.notify(db, [t.assignee_id], "due_today", t, {}, inapp=False)
        db.commit()
    except Exception:
        log.exception("noon_jobs failed")
        db.rollback()
    finally:
        db.close()


WEEKDAYS = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}


def _rule_matches(rrule: str, d: date) -> bool:
    parts = dict(p.split("=", 1) for p in rrule.split(";") if "=" in p)
    freq = parts.get("FREQ", "DAILY")
    if freq == "DAILY":
        return d.weekday() != 6  # Sunday off (6-day week)
    if freq == "WEEKLY":
        days = [WEEKDAYS[x] for x in parts.get("BYDAY", "MO").split(",") if x in WEEKDAYS]
        return d.weekday() in days
    return False


def recurring_jobs():
    """00:30 — create tasks for today from active recurring rules."""
    from ..routers.templates import render_title
    from ..routers.tasks import create_task_core
    from ..auth import Ctx
    from ..schemas import TaskCreate
    db = SessionLocal()
    try:
        today = date.today()
        for r in db.scalars(select(TaskRecurringRule).where(TaskRecurringRule.is_active == True)):  # noqa
            if not _rule_matches(r.rrule, today) or not _once(f"rrule:{r.id}"):
                continue
            tpl = db.get(TaskTemplate, r.template_id)
            if not tpl or not tpl.is_active:
                continue
            creator = db.get(User, r.reviewer_id)
            if not creator:
                continue
            ctx = Ctx(creator, "system", f"rrule-{r.id}-{today}")
            loc = db.get(Location, r.location_id) if r.location_id else None
            tc = TaskCreate(project_id=r.project_id, location_id=r.location_id, type_id=tpl.type_id,
                            title=render_title(tpl.title_pattern, {"sana": today.strftime("%d.%m")}, loc),
                            assignee_id=r.assignee_id, reviewer_id=r.reviewer_id, planned_start=today,
                            planned_end=today + timedelta(days=max(0, tpl.default_duration_days - 1)),
                            checklist=tpl.checklist_json or [], template_id=tpl.id)
            try:
                create_task_core(db, ctx, tc)
                r.next_run_at = today + timedelta(days=1)
            except Exception:
                log.exception("recurring rule %s failed", r.id)
                db.rollback()
        db.commit()
    except Exception:
        log.exception("recurring_jobs failed")
        db.rollback()
    finally:
        db.close()


def start_scheduler(tz: str):
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    sch = BackgroundScheduler(timezone=tz)
    sch.add_job(morning_jobs, CronTrigger(hour=8, minute=0), id="morning", replace_existing=True, misfire_grace_time=3600)
    sch.add_job(noon_jobs, CronTrigger(hour=12, minute=0), id="noon", replace_existing=True, misfire_grace_time=3600)
    sch.add_job(recurring_jobs, CronTrigger(hour=0, minute=30), id="recurring", replace_existing=True, misfire_grace_time=3600)
    sch.start()
    return sch
