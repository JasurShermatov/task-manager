"""Hisobot: ekranda foiz va son, kerak bo'lsa Excel yoki CSV bo'lib yuklanadi."""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import clock
from ..auth import Ctx, get_ctx
from ..db import get_db
from ..errors import validation
from ..models import DONE, MANAGERS, NEW, PROGRESS, SUBMITTED, Department, Task, User
from ..roles import role_name
from ..schemas import DashboardOut, PersonStat, ReportOut
from ..services import reports as rsvc

router = APIRouter(prefix="/reports", tags=["reports"])

PERIODS = ("week", "month", "year", "custom")


def _range(period: str, date_from: Optional[str], date_to: Optional[str]) -> tuple[date, date]:
    if period not in PERIODS:
        raise validation("VALIDATION", "Davr noto'g'ri: week, month, year yoki custom.",
                         field_errors={"period": "invalid"})
    if period == "custom":
        try:
            a, b = date.fromisoformat(date_from or ""), date.fromisoformat(date_to or "")
        except ValueError:
            raise validation("VALIDATION", "Sana oralig'ini kiriting (date_from, date_to).",
                             field_errors={"date_from": "required"})
        if b < a:
            a, b = b, a
        return a, b
    return clock.period_range(period)


@router.get("/summary", response_model=ReportOut)
def summary(ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db),
            period: str = "month", date_from: Optional[str] = None, date_to: Optional[str] = None,
            role: Optional[str] = None, department_id: Optional[int] = None):
    ctx.require_manager()
    a, b = _range(period, date_from, date_to)
    rep = rsvc.summary(db, a, b, role=role, department_id=department_id)
    return ReportOut(period=period, date_from=a, date_to=b,
                     rows=[PersonStat(**r) for r in rep["rows"]],
                     totals=PersonStat(**rep["totals"]))


@router.get("/export")
def export(ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db),
           period: str = "month", date_from: Optional[str] = None, date_to: Optional[str] = None,
           role: Optional[str] = None, department_id: Optional[int] = None,
           format: str = Query("xlsx", pattern="^(xlsx|csv)$")):
    ctx.require_manager()
    a, b = _range(period, date_from, date_to)
    rep = rsvc.summary(db, a, b, role=role, department_id=department_id)
    lang = ctx.user.lang

    def label(r: str) -> str:
        return role_name(r, lang) if r else ""

    name = f"saff-hisobot-{a}-{b}"
    if format == "csv":
        return Response(rsvc.to_csv(rep, label), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="{name}.csv"'})
    return Response(rsvc.to_xlsx(rep, label),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{name}.xlsx"'})


@router.get("/bot-summary", dependencies=[])
def bot_summary(ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db),
                period: str = "month", role: Optional[str] = None):
    """Bot uchun: tayyor matnli jadval + bir nechta raqam."""
    ctx.require_manager()
    a, b = _range(period, None, None)
    rep = rsvc.summary(db, a, b, role=role)
    return {"period": period, "date_from": a.isoformat(), "date_to": b.isoformat(),
            "table": rsvc.bot_table(rep), "totals": rep["totals"], "rows": rep["rows"][:20]}


@router.get("/person/{user_id}")
def person(user_id: int, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db),
           period: str = "month", date_from: Optional[str] = None, date_to: Optional[str] = None):
    """Bitta odamning kesimi: qaysi vazifalar kechikkan, qaysilari bajarilmagan."""
    if not ctx.is_manager and ctx.user.id != user_id:
        ctx.require_manager()
    a, b = _range(period, date_from, date_to)
    ref = clock.now()
    start, end = clock.at(a, 0, 0), clock.at(b, 23, 59)
    u = db.get(User, user_id)
    if not u:
        raise validation("NOT_FOUND", "Xodim topilmadi.")
    rows = db.scalars(select(Task).where(Task.assignee_id == user_id, Task.created_at >= start,
                                         Task.created_at <= end).order_by(Task.due_at)).all()
    def item(t: Task) -> dict:
        late = t.late_seconds(ref)
        return {"id": t.id, "code": t.code, "title": t.title, "status": t.status,
                "due_at": t.due_at.isoformat(timespec="minutes"),
                "late_days": late // 86400, "late_hours": late // 3600,
                "return_count": t.return_count}
    rep = rsvc.summary(db, a, b)
    mine = next((r for r in rep["rows"] if r["user_id"] == user_id), None)
    return {"user": {"id": u.id, "full_name": u.full_name, "role": u.role,
                     "role_name": role_name(u.role, ctx.user.lang), "position": u.position},
            "period": period, "date_from": a.isoformat(), "date_to": b.isoformat(),
            "stat": mine, "tasks": [item(t) for t in rows],
            "late": [item(t) for t in rows if t.late_seconds(ref) > 0],
            "not_done": [item(t) for t in rows if t.status in (NEW, PROGRESS) and t.due_at < ref]}


@router.get("/dashboard", response_model=DashboardOut)
def dashboard(ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    ctx.require_manager()
    ref = clock.now()
    today_a, today_b = clock.at(ref.date(), 0, 0), clock.at(ref.date(), 23, 59)

    def count(*where):
        return db.execute(select(func.count()).select_from(Task).where(*where)).scalar() or 0

    open_n = count(Task.status.in_((NEW, PROGRESS)))
    late_n = count(Task.status.in_((NEW, PROGRESS)), Task.due_at < ref)
    subm_n = count(Task.status == SUBMITTED)
    today_n = count(Task.status.in_((NEW, PROGRESS)), Task.due_at >= today_a, Task.due_at <= today_b)

    a, b = clock.period_range("month")
    rep = rsvc.summary(db, a, b)
    people = db.execute(select(func.count()).select_from(User).where(User.is_active.is_(True))).scalar() or 0
    deps = db.execute(select(func.count()).select_from(Department)
                      .where(Department.is_active.is_(True))).scalar() or 0
    return DashboardOut(open_tasks=open_n, late_tasks=late_n, submitted_tasks=subm_n, due_today=today_n,
                        done_this_month=rep["totals"]["on_time"] + rep["totals"]["late_done"],
                        percent_this_month=rep["totals"]["percent"], people=people, departments=deps)
