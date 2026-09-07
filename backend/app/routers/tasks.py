from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Optional, List

from fastapi import APIRouter, Depends, Query, UploadFile, File, Form, Response
from fastapi.responses import FileResponse
from sqlalchemy import select, or_, and_, func, desc, asc
from sqlalchemy.orm import Session

from ..auth import Ctx, get_ctx, check_task_scope, check_project_scope, location_in_scope
from ..config import settings
from ..db import get_db
from ..errors import ApiError, validation, version_conflict, not_found, permission_denied, unauthorized
from ..models import (Task, TaskType, TaskChecklistItem, TaskDependency, TaskDailyProgress, TaskAttachment,
                      TaskComment, TaskHistory, User, Location, Project, TaskTemplate, EVIDENCE_KINDS,
                      PRIORITIES)
from ..schemas import (Page, TaskCard, TaskDetail, TaskCreate, TaskPatch, TransitionIn, NoteIn, BlockIn, ReturnIn,
                       ChecklistBulk, ChecklistAdd, ChecklistItemOut, DailyIn, DailyOut, AttachmentOut,
                       CommentIn, CommentOut, HistoryOut, DependencyIn)
from ..services import tasks as svc
from ..services.enrich import build_cards, attachment_out
from ..services import files as fsvc

router = APIRouter(prefix="/tasks", tags=["tasks"])

SORTABLE = {"planned_end", "planned_start", "created_at", "updated_at", "priority", "status", "code", "title", "progress_percent"}


# ---------- scope filter for lists ----------
def scope_filter(ctx: Ctx, db: Session, q):
    u = ctx.user
    if u.role.code == "bajaruvchi":
        return q.where(or_(Task.assignee_id == u.id, Task.reviewer_id == u.id, Task.created_by == u.id))
    if u.scope_type == "system":
        return q
    if u.scope_type == "project":
        return q.where(Task.project_id == u.scope_id)
    if u.scope_type == "location":
        # all locations under scope
        ids = descendant_location_ids(db, u.scope_id)
        return q.where(or_(Task.location_id.in_(ids), Task.assignee_id == u.id, Task.reviewer_id == u.id))
    return q.where(False)


def descendant_location_ids(db: Session, root: int) -> list[int]:
    ids = [root]
    frontier = [root]
    while frontier:
        rows = db.scalars(select(Location.id).where(Location.parent_id.in_(frontier))).all()
        frontier = [r for r in rows if r not in ids]
        ids.extend(frontier)
    return ids


# ---------- list ----------
@router.get("", response_model=Page[TaskCard])
def list_tasks(ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db),
               q: Optional[str] = None, project_id: Optional[int] = None, location_id: Optional[int] = None,
               status: Optional[str] = None, priority: Optional[str] = None, type_id: Optional[int] = None,
               assignee_id: Optional[int] = None, reviewer_id: Optional[int] = None,
               overdue: Optional[bool] = None, blocked: Optional[bool] = None, mine: Optional[bool] = None,
               review_queue: Optional[bool] = None,
               date_from: Optional[date] = None, date_to: Optional[date] = None,
               limit: int = Query(100, le=200), offset: int = 0,
               sort: str = "planned_end", order: str = "asc"):
    ctx.require("tasks.read")
    stmt = select(Task).where(Task.is_active == True)  # noqa
    stmt = scope_filter(ctx, db, stmt)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Task.title.ilike(like), Task.code.ilike(like), Task.description.ilike(like)))
    if project_id:
        stmt = stmt.where(Task.project_id == project_id)
    if location_id:
        stmt = stmt.where(Task.location_id.in_(descendant_location_ids(db, location_id)))
    if status:
        stmt = stmt.where(Task.status.in_(status.split(",")))
    if priority:
        stmt = stmt.where(Task.priority.in_(priority.split(",")))
    if type_id:
        stmt = stmt.where(Task.type_id == type_id)
    if assignee_id:
        stmt = stmt.where(Task.assignee_id == assignee_id)
    if reviewer_id:
        stmt = stmt.where(Task.reviewer_id == reviewer_id)
    if mine:
        stmt = stmt.where(or_(Task.assignee_id == ctx.user.id, Task.reviewer_id == ctx.user.id))
    if review_queue:
        stmt = stmt.where(Task.status == "review", Task.reviewer_id == ctx.user.id)
    if overdue:
        stmt = stmt.where(Task.planned_end < date.today(), Task.status.notin_(("done", "cancelled")))
    if blocked:
        stmt = stmt.where(Task.status == "blocked")
    if date_from:
        stmt = stmt.where(Task.planned_end >= date_from)
    if date_to:
        stmt = stmt.where(Task.planned_start <= date_to)

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar() or 0
    col = getattr(Task, sort if sort in SORTABLE else "planned_end")
    stmt = stmt.order_by(desc(col) if order == "desc" else asc(col), Task.id).limit(limit).offset(offset)
    rows = db.scalars(stmt).all()
    return Page(items=build_cards(db, rows), total=total, limit=limit, offset=offset)


# ---------- create ----------
def _validate_people(db: Session, assignee_id: int, reviewer_id: int):
    a, r = db.get(User, assignee_id), db.get(User, reviewer_id)
    fe = {}
    if not a or not a.is_active:
        fe["assignee_id"] = "not_found"
    if not r or not r.is_active:
        fe["reviewer_id"] = "not_found"
    if fe:
        raise validation("VALIDATION", "Bajaruvchi yoki tekshiruvchi topilmadi.", field_errors=fe)
    return a, r


def _apply_checklist(db: Session, task: Task, items: list[dict]):
    for i, it in enumerate(items or []):
        title = (it.get("title") or "").strip() if isinstance(it, dict) else (it.title or "").strip()
        if not title:
            continue
        req = it.get("is_required", True) if isinstance(it, dict) else it.is_required
        db.add(TaskChecklistItem(task_id=task.id, title=title, is_required=bool(req), sort_order=i))


def create_task_core(db: Session, ctx: Ctx, body: TaskCreate) -> Task:
    ctx.require("tasks.create")
    check_project_scope(ctx, body.project_id, body.location_id, db)
    if body.priority not in PRIORITIES:
        raise validation("VALIDATION", "Muhimlik noto'g'ri.", field_errors={"priority": "invalid"})
    if body.planned_end < body.planned_start:
        raise validation("VALIDATION", "Tugash sanasi boshlanishdan oldin bo'lishi mumkin emas.",
                         field_errors={"planned_end": "before_start"})
    if not db.get(Project, body.project_id):
        raise validation("VALIDATION", "Loyiha topilmadi.", field_errors={"project_id": "not_found"})
    tt = db.get(TaskType, body.type_id)
    if not tt or not tt.is_active:
        raise validation("VALIDATION", "Ish turi topilmadi.", field_errors={"type_id": "not_found"})
    if body.location_id:
        loc = db.get(Location, body.location_id)
        if not loc or loc.project_id != body.project_id:
            raise validation("VALIDATION", "Joy loyihaga tegishli emas.", field_errors={"location_id": "invalid"})
    _validate_people(db, body.assignee_id, body.reviewer_id)

    task = Task(code=svc.next_code(db), project_id=body.project_id, location_id=body.location_id, type_id=body.type_id,
                title=body.title.strip(), description=body.description, priority=body.priority,
                assignee_id=body.assignee_id, reviewer_id=body.reviewer_id,
                planned_start=body.planned_start, planned_end=body.planned_end,
                planned_quantity=body.planned_quantity, unit=body.unit, planned_crew_size=body.planned_crew_size,
                template_id=body.template_id, created_by=ctx.user.id)
    db.add(task)
    db.flush()
    checklist = body.checklist if body.checklist is not None else (tt.default_checklist_json or [])
    _apply_checklist(db, task, [c if isinstance(c, dict) else c.model_dump() for c in checklist])
    for dep in body.depends_on or []:
        d = db.get(Task, dep)
        if not d or d.project_id != task.project_id:
            raise validation("VALIDATION", "Bog'liq vazifa topilmadi.", field_errors={"depends_on": "not_found"})
        db.add(TaskDependency(task_id=task.id, depends_on_task_id=dep))
    svc.recompute_progress(db, task)
    svc.log(db, task, "create", ctx, {}, {"title": task.title, "assignee_id": task.assignee_id,
                                          "planned_end": task.planned_end, "status": "plan"})
    svc.notify(db, [task.assignee_id], "assigned", task, {"planned_end": str(task.planned_end),
                                                          "assigned_by": ctx.user.full_name})
    if task.reviewer_id != task.assignee_id:
        svc.notify(db, [task.reviewer_id], "assigned_reviewer", task, {"planned_end": str(task.planned_end)}, telegram=False)
    return task


@router.post("", response_model=TaskDetail, status_code=201)
def create_task(body: TaskCreate, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    task = create_task_core(db, ctx, body)
    db.commit()
    return get_detail(db, ctx, task)


# ---------- detail ----------
def get_detail(db: Session, ctx: Ctx, task: Task) -> TaskDetail:
    card = build_cards(db, [task])[0]
    d = TaskDetail(**card.model_dump(), description=task.description, planned_crew_size=task.planned_crew_size,
                   template_id=task.template_id, created_by=task.created_by)
    d.checklist = [ChecklistItemOut.model_validate(i) for i in db.scalars(
        select(TaskChecklistItem).where(TaskChecklistItem.task_id == task.id).order_by(TaskChecklistItem.sort_order, TaskChecklistItem.id))]
    d.dependencies = [{"id": t.id, "code": t.code, "title": t.title, "status": t.status} for t in db.scalars(
        select(Task).join(TaskDependency, TaskDependency.depends_on_task_id == Task.id).where(TaskDependency.task_id == task.id))]
    d.dependents = [{"id": t.id, "code": t.code, "title": t.title, "status": t.status} for t in db.scalars(
        select(Task).join(TaskDependency, TaskDependency.task_id == Task.id).where(TaskDependency.depends_on_task_id == task.id))]
    atts = db.scalars(select(TaskAttachment).where(TaskAttachment.task_id == task.id, TaskAttachment.is_active == True)  # noqa
                      .order_by(TaskAttachment.created_at.desc())).all()
    users = {u.id: u for u in db.scalars(select(User).where(User.id.in_({a.uploaded_by for a in atts} or {0})))}
    d.attachments = [attachment_out(db, a, users) for a in atts]
    d.permissions = svc.task_permissions(db, ctx, task)
    d.required_evidence_kinds = svc.type_required_kinds(db, task)
    return d


def load(db: Session, ctx: Ctx, task_id: int) -> Task:
    ctx.require("tasks.read")
    t = svc.get_task_or_404(db, task_id)
    check_task_scope(ctx, t, db)
    return t


@router.get("/by-code/{code}", response_model=TaskDetail)
def get_by_code(code: str, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    t = db.scalar(select(Task).where(Task.code == code.upper().strip(), Task.is_active == True))  # noqa
    if not t:
        from ..errors import task_not_found
        raise task_not_found()
    check_task_scope(ctx, t, db)
    return get_detail(db, ctx, t)


@router.get("/{task_id}", response_model=TaskDetail)
def get_task(task_id: int, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    return get_detail(db, ctx, load(db, ctx, task_id))


# ---------- patch ----------
@router.patch("/{task_id}", response_model=TaskDetail)
def patch_task(task_id: int, body: TaskPatch, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    t = load(db, ctx, task_id)
    ctx.require("tasks.edit")
    if t.row_version != body.row_version:
        raise version_conflict()
    if t.status in ("done", "cancelled"):
        raise validation("INVALID_TRANSITION", "Yopilgan vazifani tahrirlab bo'lmaydi.")
    data = body.model_dump(exclude_unset=True, exclude={"row_version", "date_change_reason"})
    old, new = {}, {}
    if "assignee_id" in data or "reviewer_id" in data:
        ctx.require("tasks.assign")
        _validate_people(db, data.get("assignee_id", t.assignee_id), data.get("reviewer_id", t.reviewer_id))
    if "planned_start" in data or "planned_end" in data:
        ctx.require("tasks.change_dates")
        ps = data.get("planned_start", t.planned_start)
        pe = data.get("planned_end", t.planned_end)
        if pe < ps:
            raise validation("VALIDATION", "Tugash sanasi boshlanishdan oldin.", field_errors={"planned_end": "before_start"})
        if not (body.date_change_reason or "").strip():
            raise validation("VALIDATION", "Muddat o'zgarishi sababi majburiy.", field_errors={"date_change_reason": "required"})
    if "priority" in data and data["priority"] not in PRIORITIES:
        raise validation("VALIDATION", "Muhimlik noto'g'ri.", field_errors={"priority": "invalid"})
    if "location_id" in data and data["location_id"]:
        loc = db.get(Location, data["location_id"])
        if not loc or loc.project_id != t.project_id:
            raise validation("VALIDATION", "Joy loyihaga tegishli emas.", field_errors={"location_id": "invalid"})
    for k, v in data.items():
        if getattr(t, k) != v:
            old[k], new[k] = getattr(t, k), v
            setattr(t, k, v)
    if not new:
        return get_detail(db, ctx, t)
    svc.bump(t)
    if "planned_start" in new or "planned_end" in new:
        new["reason"] = body.date_change_reason
        svc.notify(db, [t.assignee_id], "dates_changed", t, {"planned_end": str(t.planned_end), "reason": body.date_change_reason}, telegram=False)
    if "assignee_id" in new:
        svc.notify(db, [t.assignee_id], "assigned", t, {"planned_end": str(t.planned_end), "assigned_by": ctx.user.full_name})
    svc.recompute_progress(db, t)
    svc.log(db, t, "update", ctx, old, new)
    db.commit()
    return get_detail(db, ctx, t)


@router.delete("/{task_id}", status_code=204)
def delete_task(task_id: int, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    t = load(db, ctx, task_id)
    ctx.require("tasks.delete")
    if t.status == "done":
        raise validation("INVALID_TRANSITION", "Bajarilgan vazifa o'chirilmaydi.")
    t.is_active = False
    svc.bump(t)
    svc.log(db, t, "delete", ctx, {"is_active": True}, {"is_active": False})
    db.commit()
    return Response(status_code=204)


# ---------- transitions ----------
@router.post("/{task_id}/transition", response_model=TaskDetail)
def transition(task_id: int, body: TransitionIn, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    t = load(db, ctx, task_id)
    svc.transition(db, ctx, t, body.to, body.note)
    db.commit()
    return get_detail(db, ctx, t)


@router.post("/{task_id}/block", response_model=TaskDetail)
def block(task_id: int, body: BlockIn, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    t = load(db, ctx, task_id)
    svc.transition(db, ctx, t, "blocked", body.note, block_reason=body.reason)
    db.commit()
    return get_detail(db, ctx, t)


@router.post("/{task_id}/unblock", response_model=TaskDetail)
def unblock(task_id: int, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    t = load(db, ctx, task_id)
    svc.transition(db, ctx, t, t.previous_status or "plan")
    db.commit()
    return get_detail(db, ctx, t)


@router.post("/{task_id}/start", response_model=TaskDetail)
def start(task_id: int, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    t = load(db, ctx, task_id)
    svc.transition(db, ctx, t, "progress")
    db.commit()
    return get_detail(db, ctx, t)


@router.post("/{task_id}/submit-review", response_model=TaskDetail)
def submit_review(task_id: int, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    t = load(db, ctx, task_id)
    svc.transition(db, ctx, t, "review")
    db.commit()
    return get_detail(db, ctx, t)


@router.post("/{task_id}/accept", response_model=TaskDetail)
def accept(task_id: int, body: NoteIn = NoteIn(), ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    t = load(db, ctx, task_id)
    svc.transition(db, ctx, t, "done", body.note)
    db.commit()
    return get_detail(db, ctx, t)


@router.post("/{task_id}/return", response_model=TaskDetail)
def return_task(task_id: int, body: ReturnIn, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    t = load(db, ctx, task_id)
    if t.status != "review":
        from ..errors import invalid_transition
        raise invalid_transition(t.status, "progress")
    svc.transition(db, ctx, t, "progress", body.reason)
    db.commit()
    return get_detail(db, ctx, t)


@router.post("/{task_id}/reopen", response_model=TaskDetail)
def reopen(task_id: int, body: NoteIn = NoteIn(), ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    t = load(db, ctx, task_id)
    if t.status != "done":
        from ..errors import invalid_transition
        raise invalid_transition(t.status, "progress")
    svc.transition(db, ctx, t, "progress", body.note)
    db.commit()
    return get_detail(db, ctx, t)


# ---------- checklist ----------
def _can_act(ctx: Ctx, t: Task):
    if ctx.user.role.code == "bajaruvchi" and t.assignee_id != ctx.user.id:
        raise ApiError(403, "SCOPE_FORBIDDEN", "Bu vazifa sizga biriktirilmagan.")


@router.get("/{task_id}/checklist", response_model=List[ChecklistItemOut])
def checklist(task_id: int, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    t = load(db, ctx, task_id)
    return db.scalars(select(TaskChecklistItem).where(TaskChecklistItem.task_id == t.id)
                      .order_by(TaskChecklistItem.sort_order, TaskChecklistItem.id)).all()


@router.patch("/{task_id}/checklist", response_model=TaskDetail)
def checklist_bulk(task_id: int, body: ChecklistBulk, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    t = load(db, ctx, task_id)
    ctx.require("checklist.edit")
    _can_act(ctx, t)
    if t.status in ("done", "cancelled"):
        raise validation("INVALID_TRANSITION", "Yopilgan vazifa checklisti o'zgarmaydi.")
    changed = {}
    for it in body.items:
        item = db.get(TaskChecklistItem, int(it["id"]))
        if not item or item.task_id != t.id:
            continue
        val = bool(it.get("is_done"))
        if item.is_done != val:
            item.is_done = val
            item.done_by = ctx.user.id if val else None
            item.done_at = datetime.utcnow() if val else None
            changed[item.title] = val
    if changed:
        svc.recompute_progress(db, t)
        svc.bump(t)
        svc.log(db, t, "checklist", ctx, {}, changed)
        db.commit()
    return get_detail(db, ctx, t)


@router.post("/{task_id}/checklist", response_model=TaskDetail, status_code=201)
def checklist_add(task_id: int, body: ChecklistAdd, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    t = load(db, ctx, task_id)
    ctx.require("checklist.edit")
    _can_act(ctx, t)
    mx = db.execute(select(func.coalesce(func.max(TaskChecklistItem.sort_order), -1)).where(TaskChecklistItem.task_id == t.id)).scalar()
    db.add(TaskChecklistItem(task_id=t.id, title=body.title.strip(), is_required=body.is_required, sort_order=mx + 1))
    svc.recompute_progress(db, t)
    svc.bump(t)
    svc.log(db, t, "checklist_add", ctx, {}, {"title": body.title})
    db.commit()
    return get_detail(db, ctx, t)


# ---------- daily progress ----------
@router.get("/{task_id}/daily-progress", response_model=List[DailyOut])
def daily_list(task_id: int, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    t = load(db, ctx, task_id)
    rows = db.scalars(select(TaskDailyProgress).where(TaskDailyProgress.task_id == t.id)
                      .order_by(TaskDailyProgress.date.desc(), TaskDailyProgress.id.desc())).all()
    users = {u.id: u for u in db.scalars(select(User).where(User.id.in_({r.created_by for r in rows} or {0})))}
    out = []
    for r in rows:
        o = DailyOut.model_validate(r)
        o.created_by_name = users[r.created_by].full_name if r.created_by in users else ""
        out.append(o)
    return out


@router.post("/{task_id}/daily-progress", response_model=DailyOut, status_code=201)
def daily_add(task_id: int, body: DailyIn, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    t = load(db, ctx, task_id)
    ctx.require("progress.create")
    _can_act(ctx, t)
    if t.status not in ("progress", "blocked", "review"):
        raise validation("INVALID_TRANSITION", "Kunlik hisobot faqat jarayondagi vazifaga qo'shiladi.")
    dup = db.scalar(select(TaskDailyProgress).where(TaskDailyProgress.task_id == t.id, TaskDailyProgress.date == body.date,
                                                   TaskDailyProgress.is_duplicate == False))  # noqa
    row = TaskDailyProgress(task_id=t.id, date=body.date, quantity=body.quantity, workers_count=body.workers_count,
                            work_hours=body.work_hours, note=body.note, source=ctx.source, created_by=ctx.user.id,
                            is_duplicate=bool(dup))
    db.add(row)
    db.flush()
    svc.recompute_quantity(db, t)
    svc.bump(t)
    svc.log(db, t, "daily_progress", ctx, {}, {"date": body.date, "quantity": body.quantity,
                                               "workers": body.workers_count, "duplicate": bool(dup)})
    # the report must reach the people who supervise this task: prorab, rahbar and the reviewer
    watchers = svc.prorab_and_rahbar_ids(db, t) | {t.reviewer_id}
    watchers.discard(ctx.user.id)
    svc.notify(db, watchers, "daily_report", t, {
        "date": str(body.date), "quantity": float(body.quantity) if body.quantity is not None else None,
        "unit": t.unit or "", "workers": body.workers_count, "note": (body.note or "")[:200],
        "by": ctx.user.full_name, "total": float(t.actual_quantity or 0),
        "plan": float(t.planned_quantity) if t.planned_quantity else None,
        "duplicate": bool(dup),
    })
    db.commit()
    o = DailyOut.model_validate(row)
    o.created_by_name = ctx.user.full_name
    return o


# ---------- attachments ----------
@router.post("/{task_id}/attachments", response_model=AttachmentOut, status_code=201)
async def upload(task_id: int, file: UploadFile = File(...), kind: str = Form("during"),
                 daily_progress_id: Optional[int] = Form(None), captured_at: Optional[datetime] = Form(None),
                 ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    t = load(db, ctx, task_id)
    ctx.require("attachments.upload")
    _can_act(ctx, t)
    if t.status in ("done", "cancelled"):
        raise validation("INVALID_TRANSITION", "Yopilgan vazifaga fayl qo'shib bo'lmaydi.")
    if kind not in EVIDENCE_KINDS:
        raise validation("VALIDATION", "Fayl turi noto'g'ri.", field_errors={"kind": "invalid"})
    mime = (file.content_type or "").lower()
    if mime not in fsvc.ALLOWED:
        raise ApiError(415, "FILE_TYPE_NOT_ALLOWED", "Bu turdagi fayl qabul qilinmaydi.")
    data = await file.read()
    limit = settings.MAX_IMAGE_MB if mime in fsvc.IMAGE_MIMES else settings.MAX_DOC_MB
    if len(data) > limit * 1024 * 1024:
        raise ApiError(413, "FILE_TOO_LARGE", "Fayl hajmi chegaradan katta.")
    if kind == "document" and mime in fsvc.IMAGE_MIMES:
        pass
    if kind != "document" and mime not in fsvc.IMAGE_MIMES:
        raise ApiError(415, "FILE_TYPE_NOT_ALLOWED", "Foto turiga faqat rasm yuklanadi.")
    key = fsvc.store(data, file.filename or "file")
    att = TaskAttachment(task_id=t.id, daily_progress_id=daily_progress_id, kind=kind, storage_key=key,
                         filename=file.filename or "file", mime_type=mime, size=len(data),
                         captured_at=captured_at, source=ctx.source, uploaded_by=ctx.user.id)
    db.add(att)
    db.flush()
    svc.bump(t)
    svc.log(db, t, "attach", ctx, {}, {"kind": kind, "filename": att.filename, "size": att.size})
    db.commit()
    return attachment_out(db, att)


@router.delete("/{task_id}/attachments/{att_id}", status_code=204)
def delete_attachment(task_id: int, att_id: int, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    t = load(db, ctx, task_id)
    att = db.get(TaskAttachment, att_id)
    if not att or att.task_id != t.id or not att.is_active:
        raise not_found("Fayl")
    if t.status == "done":
        raise validation("INVALID_TRANSITION", "Bajarilgan vazifa fayllari o'chirilmaydi.")
    if not (ctx.has("attachments.delete") or att.uploaded_by == ctx.user.id):
        raise permission_denied()
    att.is_active = False
    svc.bump(t)
    svc.log(db, t, "attachment_delete", ctx, {"filename": att.filename, "kind": att.kind}, {})
    db.commit()
    return Response(status_code=204)


# ---------- comments ----------
MENTION_RE = re.compile(r"@([\w.\-]+)")


@router.get("/{task_id}/comments", response_model=List[CommentOut])
def comments(task_id: int, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    t = load(db, ctx, task_id)
    rows = db.scalars(select(TaskComment).where(TaskComment.task_id == t.id).order_by(TaskComment.created_at)).all()
    users = {u.id: u for u in db.scalars(select(User).where(User.id.in_({r.author_id for r in rows} or {0})))}
    out = []
    for r in rows:
        o = CommentOut.model_validate(r)
        o.author_name = users[r.author_id].full_name if r.author_id in users else ""
        out.append(o)
    return out


@router.post("/{task_id}/comments", response_model=CommentOut, status_code=201)
def comment_add(task_id: int, body: CommentIn, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    t = load(db, ctx, task_id)
    ctx.require("comments.create")
    handles = MENTION_RE.findall(body.text)
    mentioned = db.scalars(select(User).where(User.login.in_(handles))).all() if handles else []
    c = TaskComment(task_id=t.id, text=body.text.strip(), author_id=ctx.user.id,
                    mentions_json=[u.id for u in mentioned], source=ctx.source)
    db.add(c)
    db.flush()
    svc.log(db, t, "comment", ctx, {}, {"text": body.text[:200]})
    targets = {u.id for u in mentioned}
    svc.notify(db, targets, "mentioned", t, {"by": ctx.user.full_name, "text": body.text[:200]})
    # non-mention comment notify: assignee & reviewer (in-app + telegram)
    others = {t.assignee_id, t.reviewer_id} - {ctx.user.id} - targets
    svc.notify(db, others, "comment", t, {"by": ctx.user.full_name, "text": body.text[:200]})
    db.commit()
    o = CommentOut.model_validate(c)
    o.author_name = ctx.user.full_name
    return o


# ---------- history ----------
@router.get("/{task_id}/history", response_model=List[HistoryOut])
def history(task_id: int, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    t = load(db, ctx, task_id)
    rows = db.scalars(select(TaskHistory).where(TaskHistory.task_id == t.id).order_by(TaskHistory.created_at.desc(), TaskHistory.id.desc())).all()
    users = {u.id: u for u in db.scalars(select(User).where(User.id.in_({r.actor_id for r in rows if r.actor_id} or {0})))}
    out = []
    for r in rows:
        o = HistoryOut.model_validate(r)
        o.actor_name = users[r.actor_id].full_name if r.actor_id in users else "Tizim"
        out.append(o)
    return out


# ---------- dependencies ----------
@router.post("/{task_id}/dependencies", response_model=TaskDetail, status_code=201)
def dep_add(task_id: int, body: DependencyIn, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    t = load(db, ctx, task_id)
    ctx.require("tasks.edit")
    d = svc.get_task_or_404(db, body.depends_on_task_id)
    if d.id == t.id or d.project_id != t.project_id:
        raise validation("VALIDATION", "Bog'liqlik noto'g'ri.")
    if svc.has_cycle(db, t.id, d.id):
        raise validation("DEPENDENCY_CYCLE", "Bog'liqlikda halqa hosil bo'ladi.")
    if not db.get(TaskDependency, (t.id, d.id)):
        db.add(TaskDependency(task_id=t.id, depends_on_task_id=d.id))
        svc.bump(t)
        svc.log(db, t, "dependency_add", ctx, {}, {"depends_on": d.code})
        db.commit()
    return get_detail(db, ctx, t)


@router.delete("/{task_id}/dependencies/{dep_id}", response_model=TaskDetail)
def dep_del(task_id: int, dep_id: int, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    t = load(db, ctx, task_id)
    ctx.require("tasks.edit")
    row = db.get(TaskDependency, (t.id, dep_id))
    if row:
        db.delete(row)
        svc.bump(t)
        svc.log(db, t, "dependency_remove", ctx, {"depends_on": dep_id}, {})
        db.commit()
    return get_detail(db, ctx, t)
