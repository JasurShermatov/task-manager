from __future__ import annotations

import csv
import io
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from ..auth import Ctx, get_ctx
from ..db import get_db
from ..models import Task, User, TaskType, TaskHistory
from ..services.enrich import build_cards
from .tasks import scope_filter, descendant_location_ids

router = APIRouter(prefix="/reports", tags=["reports"])

BLOCK_LABELS = {"material_yoq": "Material yo'q", "hujjat_kutilmoqda": "Hujjat kutilmoqda", "texnika_band": "Texnika band",
                "ishchi_yetmadi": "Ishchi kuchi yetmadi", "oldingi_ish": "Oldingi ish tugamagan", "obhavo": "Ob-havo",
                "qaror_kutilmoqda": "Qaror kutilmoqda", "boshqa": "Boshqa"}


def _base(ctx, db, project_id, location_id, date_from, date_to):
    q = select(Task).where(Task.is_active == True)  # noqa
    q = scope_filter(ctx, db, q)
    if project_id:
        q = q.where(Task.project_id == project_id)
    if location_id:
        q = q.where(Task.location_id.in_(descendant_location_ids(db, location_id)))
    if date_from:
        q = q.where(Task.planned_end >= date_from)
    if date_to:
        q = q.where(Task.planned_start <= date_to)
    return db.scalars(q).all()


@router.get("/summary")
def summary(ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db), project_id: Optional[int] = None,
            location_id: Optional[int] = None, date_from: Optional[date] = None, date_to: Optional[date] = None):
    ctx.require("reports.read")
    tasks = _base(ctx, db, project_id, location_id, date_from, date_to)
    today = date.today()
    now = datetime.utcnow()
    open_ = [t for t in tasks if t.status in ("plan", "progress", "review", "blocked")]
    overdue = [t for t in tasks if t.planned_end < today and t.status not in ("done", "cancelled")]
    overdue_assignee = [t for t in overdue if t.status != "review"]
    overdue_reviewer = [t for t in overdue if t.status == "review"]
    blocked = [t for t in tasks if t.status == "blocked"]
    review = [t for t in tasks if t.status == "review"]
    done = [t for t in tasks if t.status == "done"]
    on_time = [t for t in done if t.actual_end and t.actual_end.date() <= t.planned_end]
    durations = [(t.actual_end - t.actual_start).total_seconds() / 86400 for t in done if t.actual_end and t.actual_start]
    review_ages = [(now - t.review_started_at).days for t in review if t.review_started_at]

    by_status = {s: sum(1 for t in tasks if t.status == s) for s in ("plan", "progress", "review", "done", "blocked", "cancelled")}
    blocked_reasons = {}
    for t in blocked:
        r = blocked_reasons.setdefault(t.blocked_reason or "boshqa", {"code": t.blocked_reason or "boshqa", "label": BLOCK_LABELS.get(t.blocked_reason or "boshqa"), "count": 0, "days": 0})
        r["count"] += 1
        r["days"] += (now - t.blocked_at).days if t.blocked_at else 0
    # historical block days by reason (from history)
    tids = [t.id for t in tasks] or [0]
    for h in db.scalars(select(TaskHistory).where(TaskHistory.task_id.in_(tids), TaskHistory.action == "block")):
        code = (h.new_values_json or {}).get("reason", "boshqa")
        r = blocked_reasons.setdefault(code, {"code": code, "label": BLOCK_LABELS.get(code, code), "count": 0, "days": 0})
        r["hist"] = r.get("hist", 0) + 1

    users = {u.id: u for u in db.scalars(select(User))}
    staff = {}
    for t in tasks:
        s = staff.setdefault(t.assignee_id, {"user_id": t.assignee_id, "name": users[t.assignee_id].full_name if t.assignee_id in users else "?",
                                             "total": 0, "done": 0, "on_time": 0, "returned": 0, "overdue": 0, "open": 0})
        s["total"] += 1
        if t.status == "done":
            s["done"] += 1
            if t.actual_end and t.actual_end.date() <= t.planned_end:
                s["on_time"] += 1
        if t.return_count > 0:
            s["returned"] += 1
        if t in overdue_assignee:
            s["overdue"] += 1
        if t.status in ("plan", "progress", "review", "blocked"):
            s["open"] += 1
    for s in staff.values():
        s["on_time_pct"] = round(s["on_time"] / s["done"] * 100) if s["done"] else None
        s["return_pct"] = round(s["returned"] / s["total"] * 100) if s["total"] else 0

    reviewers = {}
    for t in tasks:
        r = reviewers.setdefault(t.reviewer_id, {"user_id": t.reviewer_id, "name": users[t.reviewer_id].full_name if t.reviewer_id in users else "?",
                                                 "queue": 0, "review_durations": []})
        if t.status == "review":
            r["queue"] += 1
    for h in db.scalars(select(TaskHistory).where(TaskHistory.task_id.in_(tids), TaskHistory.action.in_(("accept", "return")))):
        pass
    for r in reviewers.values():
        r.pop("review_durations", None)

    daily = []
    for i in range(13, -1, -1):
        d = today - timedelta(days=i)
        daily.append({"date": str(d), "done": sum(1 for t in done if t.actual_end and t.actual_end.date() == d)})

    return {
        "kpi": {
            "open": len(open_), "overdue": len(overdue), "overdue_by_assignee": len(overdue_assignee),
            "overdue_by_reviewer": len(overdue_reviewer), "blocked": len(blocked), "review": len(review),
            "review_oldest_days": max(review_ages) if review_ages else 0,
            "done": len(done), "on_time_pct": round(len(on_time) / len(done) * 100) if done else None,
            "avg_duration_days": round(sum(durations) / len(durations), 1) if durations else None,
            "return_pct": round(sum(1 for t in tasks if t.return_count > 0) / len(tasks) * 100) if tasks else 0,
            "total": len(tasks),
        },
        "by_status": by_status,
        "blocked_reasons": sorted(blocked_reasons.values(), key=lambda r: -r["count"]),
        "staff": sorted(staff.values(), key=lambda s: -s["total"]),
        "reviewers": sorted(reviewers.values(), key=lambda r: -r["queue"]),
        "daily_done": daily,
    }


@router.get("/export.csv")
def export_csv(ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db), project_id: Optional[int] = None,
               location_id: Optional[int] = None, status: Optional[str] = None, assignee_id: Optional[int] = None,
               overdue: Optional[bool] = None, blocked: Optional[bool] = None, q: Optional[str] = None,
               date_from: Optional[date] = None, date_to: Optional[date] = None, lang: str = "uz"):
    ctx.require("tasks.export")
    tasks = _base(ctx, db, project_id, location_id, date_from, date_to)
    today = date.today()
    if status:
        tasks = [t for t in tasks if t.status in status.split(",")]
    if assignee_id:
        tasks = [t for t in tasks if t.assignee_id == assignee_id]
    if overdue:
        tasks = [t for t in tasks if t.planned_end < today and t.status not in ("done", "cancelled")]
    if blocked:
        tasks = [t for t in tasks if t.status == "blocked"]
    if q:
        ql = q.lower()
        tasks = [t for t in tasks if ql in t.title.lower() or ql in t.code.lower()]
    cards = build_cards(db, tasks, today)
    HEAD = {
        "uz": ["Kod", "Sarlavha", "Loyiha", "Joy", "Ish turi", "Holat", "Muhimlik", "Bajaruvchi", "Tekshiruvchi", "Reja boshi", "Reja oxiri",
               "Fakt boshi", "Fakt oxiri", "Progress %", "Reja hajm", "Fakt hajm", "Birlik", "Checklist", "Foto", "Kechikish (kun)", "Blok sababi", "Qaytarilgan"],
        "ru": ["Код", "Название", "Проект", "Место", "Вид работ", "Статус", "Приоритет", "Исполнитель", "Проверяющий", "План начало", "План конец",
               "Факт начало", "Факт конец", "Прогресс %", "План объём", "Факт объём", "Ед.", "Чеклист", "Фото", "Просрочка (дн)", "Причина блока", "Возвраты"],
        "en": ["Code", "Title", "Project", "Location", "Work type", "Status", "Priority", "Assignee", "Reviewer", "Plan start", "Plan end",
               "Actual start", "Actual end", "Progress %", "Plan qty", "Actual qty", "Unit", "Checklist", "Photos", "Overdue (d)", "Block reason", "Returns"],
    }
    buf = io.StringIO()
    buf.write("﻿")
    w = csv.writer(buf, delimiter=";")
    w.writerow(HEAD.get(lang, HEAD["uz"]))
    for c in cards:
        w.writerow([c.code, c.title, c.project_name, " / ".join(p.name for p in c.location_path), c.type_name, c.status, c.priority,
                    c.assignee_name, c.reviewer_name, c.planned_start, c.planned_end,
                    c.actual_start.date() if c.actual_start else "", c.actual_end.date() if c.actual_end else "",
                    c.progress_percent, c.planned_quantity or "", c.actual_quantity or "", c.unit or "",
                    f"{c.checklist_done}/{c.checklist_total}", c.photos_count, c.overdue_days, c.blocked_reason or "", c.return_count])
    buf.seek(0)
    fname = f"vazifalar_{today.isoformat()}.csv"
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": f'attachment; filename="{fname}"'})
