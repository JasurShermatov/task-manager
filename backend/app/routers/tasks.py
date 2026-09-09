"""Vazifa oqimi: berish -> boshlash -> dalil bilan topshirish -> qabul / qayta qil."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .. import clock
from ..auth import Ctx, check_task_access, get_ctx
from ..config import settings
from ..db import get_db
from ..errors import invalid_transition, not_found, permission_denied, task_not_found, validation, version_conflict
from ..models import (
    CANCELLED, DONE, NEW, PROGRESS, SUBMITTED, Department, Task, TaskComment, TaskFile, TaskHistory, User,
)
from ..schemas import CommentIn, CommentOut, FileOut, HistoryOut, ReasonIn, SubmitIn, TaskIn, TaskListOut, TaskOut, TaskPatch
from ..services import files as fsvc
from ..services import tasks as svc

router = APIRouter(tags=["tasks"])


def _get(db: Session, ctx: Ctx, task_id: int) -> Task:
    t = db.get(Task, task_id)
    if not t:
        raise task_not_found()
    check_task_access(ctx, t)
    return t


def _one(db: Session, ctx: Ctx, t: Task) -> TaskOut:
    row = svc.enrich(db, [t], ctx)[0]
    return TaskOut(**svc.with_files(db, row, t))


def _assignee(db: Session, assignee_id: int) -> User:
    u = db.get(User, assignee_id)
    if not u or not u.is_active:
        raise validation("VALIDATION", "Bunday xodim topilmadi yoki u faol emas.",
                         field_errors={"assignee_id": "not_found"})
    return u


def _due(value, field: str = "due_at") -> datetime:
    due = clock.parse_due(value)
    if not due:
        raise validation("VALIDATION", "Muddat noto'g'ri. Masalan: 2026-09-10 yoki 2026-09-10T14:00.",
                         field_errors={field: "invalid"})
    return due


# ---------------------------------------------------------------- ro'yxat
@router.get("/tasks", response_model=TaskListOut)
def list_tasks(ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db),
               status: Optional[str] = None, assignee_id: Optional[int] = None,
               department_id: Optional[int] = None, overdue: Optional[bool] = None,
               date_from: Optional[str] = None, date_to: Optional[str] = None,
               q: Optional[str] = None, mine: bool = False,
               page: int = 1, per_page: int = Query(50, le=200)):
    """`mine=true` — faqat menga berilgan vazifalar. Boshliq va assistant bir-biriga
    vazifa bera oladi, shuning uchun ularga ham «Vazifalarim» kerak: shu bayroqsiz
    boshqaruvchi hamma vazifani ko'rar edi."""
    ref = clock.now()
    sel = select(Task)
    if mine or not ctx.is_manager:
        sel = sel.where(Task.assignee_id == ctx.user.id)   # ijrochi faqat o'zinikini ko'radi
    if status:
        sel = sel.where(Task.status.in_([s.strip() for s in status.split(",") if s.strip()]))
    if assignee_id:
        sel = sel.where(Task.assignee_id == assignee_id)
    if department_id:
        ids = [u.id for u in db.scalars(select(User).where(User.department_id == department_id))]
        sel = sel.where(Task.assignee_id.in_(ids or [0]))
    if overdue:
        sel = sel.where(Task.status.in_((NEW, PROGRESS)), Task.due_at < ref)
    if date_from:
        sel = sel.where(Task.due_at >= clock.at(clock.parse_due(date_from).date(), 0, 0))
    if date_to:
        sel = sel.where(Task.due_at <= clock.at(clock.parse_due(date_to).date(), 23, 59))
    if q:
        like = f"%{q.strip().lower()}%"
        sel = sel.where(or_(func.lower(Task.title).like(like), func.lower(Task.code).like(like)))

    total = db.execute(select(func.count()).select_from(sel.subquery())).scalar() or 0
    page = max(1, page)
    rows = db.scalars(sel.order_by(Task.due_at.asc(), Task.id.desc())
                      .offset((page - 1) * per_page).limit(per_page)).all()
    return TaskListOut(items=[TaskOut(**r) for r in svc.enrich(db, rows, ctx)],
                       total=total, page=page, per_page=per_page)


@router.get("/tasks/by-code/{code}", response_model=TaskOut)
def by_code(code: str, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    t = db.scalar(select(Task).where(func.upper(Task.code) == code.strip().upper()))
    if not t:
        raise task_not_found()
    check_task_access(ctx, t)
    return _one(db, ctx, t)


@router.get("/tasks/{task_id}", response_model=TaskOut)
def get_task(task_id: int, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    return _one(db, ctx, _get(db, ctx, task_id))


# ---------------------------------------------------------------- yaratish va tahrirlash
@router.post("/tasks", response_model=TaskOut, status_code=201)
def create_task(body: TaskIn, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    ctx.require_manager()
    _assignee(db, body.assignee_id)
    due = _due(body.due_at)
    t = Task(code=svc.next_code(db), title=body.title.strip(),
             description=(body.description or "").strip() or None,
             assignee_id=body.assignee_id, created_by=ctx.user.id,
             due_at=due, original_due_at=due, status=NEW)
    db.add(t)
    db.flush()
    svc.log(db, t, "create", ctx, new={"title": t.title, "assignee_id": t.assignee_id,
                                       "due_at": due.isoformat(timespec="minutes")})
    svc.notify(db, t.assignee_id, "task_created", t,
               svc.task_payload(db, t, actor_name=ctx.user.full_name))
    db.commit()
    db.refresh(t)
    return _one(db, ctx, t)


@router.patch("/tasks/{task_id}", response_model=TaskOut)
def update_task(task_id: int, body: TaskPatch, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    ctx.require_manager()
    t = _get(db, ctx, task_id)
    if t.status in (DONE, CANCELLED):
        raise invalid_transition(t.status, "edit")
    if body.row_version is not None and body.row_version != t.row_version:
        raise version_conflict()

    data = body.model_dump(exclude_unset=True)
    old, new = {}, {}
    if data.get("title"):
        old["title"], t.title, new["title"] = t.title, data["title"].strip(), data["title"].strip()
    if "description" in data:
        t.description = (data["description"] or "").strip() or None
        new["description"] = t.description
    if data.get("assignee_id") and data["assignee_id"] != t.assignee_id:
        _assignee(db, data["assignee_id"])
        old["assignee_id"], previous = t.assignee_id, t.assignee_id
        t.assignee_id = data["assignee_id"]
        new["assignee_id"] = t.assignee_id
        svc.notify(db, previous, "task_unassigned", t, svc.task_payload(db, t, actor_name=ctx.user.full_name))
        svc.notify(db, t.assignee_id, "task_created", t, svc.task_payload(db, t, actor_name=ctx.user.full_name))
    if data.get("due_at"):
        due = _due(data["due_at"])
        if due != t.due_at:
            old["due_at"] = t.due_at.isoformat(timespec="minutes")
            t.due_at = due
            t.due_changed_count += 1
            new["due_at"] = due.isoformat(timespec="minutes")
            svc.notify(db, t.assignee_id, "due_changed", t,
                       svc.task_payload(db, t, actor_name=ctx.user.full_name, old_due=old["due_at"]))
    if new:
        t.row_version += 1
        svc.log(db, t, "update", ctx, old=old, new=new)
    db.commit()
    db.refresh(t)
    return _one(db, ctx, t)


# ---------------------------------------------------------------- oqim
@router.post("/tasks/{task_id}/start", response_model=TaskOut)
def start(task_id: int, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    t = _get(db, ctx, task_id)
    if t.assignee_id != ctx.user.id:
        raise permission_denied()
    if t.status != NEW:
        raise invalid_transition(t.status, PROGRESS)
    t.status, t.started_at = PROGRESS, clock.now()
    svc.log(db, t, "start", ctx)
    svc.notify_managers(db, "task_started", t, exclude=ctx.user.id, actor_name=ctx.user.full_name)
    db.commit()
    db.refresh(t)
    return _one(db, ctx, t)


def _fresh_proofs(db: Session, t: Task) -> int:
    """Qaytarilgandan keyin qo'yilgan dalillar. Eski dalil bilan qayta topshirib bo'lmaydi."""
    since = t.last_returned_at or t.created_at
    return db.execute(select(func.count()).select_from(TaskFile).where(
        TaskFile.task_id == t.id, TaskFile.kind == "proof", TaskFile.is_active.is_(True),
        TaskFile.created_at >= since)).scalar() or 0


@router.post("/tasks/{task_id}/submit", response_model=TaskOut)
def submit(task_id: int, body: SubmitIn, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    """Topshirish — dalilsiz bo'lmaydi. Fayllar avval /tasks/{id}/files ga yuklanadi."""
    t = _get(db, ctx, task_id)
    if t.assignee_id != ctx.user.id:
        raise permission_denied()
    if t.status not in (NEW, PROGRESS):
        raise invalid_transition(t.status, SUBMITTED)
    if not _fresh_proofs(db, t):
        raise validation("PROOF_REQUIRED",
                         "Dalil kerak: kamida bitta rasm yoki fayl biriktiring.",
                         field_errors={"files": "required"})
    t.status, t.submitted_at = SUBMITTED, clock.now()
    t.submit_note = body.note.strip()
    svc.log(db, t, "submit", ctx, new={"note": t.submit_note})
    late = t.late_seconds(clock.now())
    svc.notify_managers(db, "task_submitted", t, exclude=ctx.user.id,
                        actor_name=ctx.user.full_name, note=t.submit_note,
                        on_time=late == 0, proof_count=_fresh_proofs(db, t))
    db.commit()
    db.refresh(t)
    return _one(db, ctx, t)


@router.post("/tasks/{task_id}/accept", response_model=TaskOut)
def accept(task_id: int, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    ctx.require_manager()
    t = _get(db, ctx, task_id)
    if t.status != SUBMITTED:
        raise invalid_transition(t.status, DONE)
    # O'zining ishini o'zi qabul qilishi tekshiruvni ma'nosiz qiladi: vazifani bergan
    # ikkinchi boshqaruvchi qabul qiladi. O'ziga o'zi qo'ygan vazifa bundan mustasno.
    if t.assignee_id == ctx.user.id and t.created_by != ctx.user.id:
        raise validation("SELF_ACCEPT",
                         "O'zingizga berilgan vazifani o'zingiz qabul qila olmaysiz — "
                         "uni bergan odam qabul qiladi.")
    t.status, t.done_at, t.accepted_by = DONE, clock.now(), ctx.user.id
    svc.log(db, t, "accept", ctx)
    svc.notify(db, t.assignee_id, "task_accepted", t, svc.task_payload(db, t, actor_name=ctx.user.full_name))
    db.commit()
    db.refresh(t)
    return _one(db, ctx, t)


@router.post("/tasks/{task_id}/return", response_model=TaskOut)
def return_task(task_id: int, body: ReasonIn, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    """Qayta qil — sabab majburiy, aks holda ijrochi nimani tuzatishni bilmaydi."""
    ctx.require_manager()
    t = _get(db, ctx, task_id)
    if t.status != SUBMITTED:
        raise invalid_transition(t.status, PROGRESS)
    reason = body.reason.strip()
    t.status, t.submitted_at, t.submit_note = PROGRESS, None, None
    t.return_count += 1
    t.last_returned_at = clock.now()
    db.add(TaskComment(task_id=t.id, text=f"↩️ {reason}", author_id=ctx.user.id, source=ctx.source))
    svc.log(db, t, "return", ctx, new={"reason": reason, "return_count": t.return_count})
    svc.notify(db, t.assignee_id, "task_returned", t,
               svc.task_payload(db, t, actor_name=ctx.user.full_name, reason=reason))
    db.commit()
    db.refresh(t)
    return _one(db, ctx, t)


@router.post("/tasks/{task_id}/cancel", response_model=TaskOut)
def cancel(task_id: int, body: ReasonIn, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    ctx.require_manager()
    t = _get(db, ctx, task_id)
    if t.status in (DONE, CANCELLED):
        raise invalid_transition(t.status, CANCELLED)
    t.status, t.cancelled_at = CANCELLED, clock.now()
    svc.log(db, t, "cancel", ctx, new={"reason": body.reason.strip()})
    svc.notify(db, t.assignee_id, "task_cancelled", t,
               svc.task_payload(db, t, actor_name=ctx.user.full_name, reason=body.reason.strip()))
    db.commit()
    db.refresh(t)
    return _one(db, ctx, t)


# ---------------------------------------------------------------- fayllar va izohlar
@router.post("/tasks/{task_id}/files", response_model=FileOut, status_code=201)
async def upload(task_id: int, file: UploadFile = File(...), kind: str = Form("proof"),
                 ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    t = _get(db, ctx, task_id)
    if not (ctx.is_manager or t.assignee_id == ctx.user.id):
        raise permission_denied()
    if kind not in ("proof", "task"):
        kind = "proof"
    data = await file.read()
    mime = file.content_type or "application/octet-stream"
    limit = settings.MAX_IMAGE_MB if mime.startswith("image/") else settings.MAX_DOC_MB
    if len(data) > limit * 1024 * 1024:
        raise validation("FILE_TOO_LARGE", f"Fayl {limit} MB dan katta bo'lmasligi kerak.",
                         field_errors={"file": "too_large"}, limit_mb=limit)
    if mime not in fsvc.ALLOWED and not mime.startswith("image/"):
        raise validation("FILE_TYPE", "Bu turdagi fayl qabul qilinmaydi.", field_errors={"file": "type"})
    key = fsvc.store(data, file.filename or "file")
    row = TaskFile(task_id=t.id, kind=kind, storage_key=key, filename=(file.filename or "file")[:250],
                   mime_type=mime, size=len(data), uploaded_by=ctx.user.id, source=ctx.source)
    db.add(row)
    db.commit()
    db.refresh(row)
    return FileOut(id=row.id, kind=row.kind, filename=row.filename, mime_type=row.mime_type,
                   size=row.size, url=fsvc.signed_url(row.id), created_at=row.created_at)


@router.delete("/tasks/{task_id}/files/{file_id}")
def delete_file(task_id: int, file_id: int, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    t = _get(db, ctx, task_id)
    row = db.get(TaskFile, file_id)
    if not row or row.task_id != t.id or not row.is_active:
        raise not_found("Fayl")
    if not (ctx.is_manager or row.uploaded_by == ctx.user.id):
        raise permission_denied()
    row.is_active = False
    db.commit()
    return {"ok": True}


@router.post("/tasks/{task_id}/comments", response_model=CommentOut, status_code=201)
def comment(task_id: int, body: CommentIn, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    """Ijrochi «material yo'q» deb yozsa — boss va assistantga darhol boradi.
    Alohida «muammo» holati o'rniga shu ishlatiladi."""
    t = _get(db, ctx, task_id)
    row = TaskComment(task_id=t.id, text=body.text.strip(), author_id=ctx.user.id, source=ctx.source)
    db.add(row)
    db.flush()
    payload = svc.task_payload(db, t, actor_name=ctx.user.full_name, text=row.text)
    if ctx.is_manager:
        svc.notify(db, t.assignee_id, "comment", t, payload)
    else:
        svc.notify_managers(db, "comment", t, exclude=ctx.user.id,
                            actor_name=ctx.user.full_name, text=row.text)
    db.commit()
    db.refresh(row)
    return CommentOut(id=row.id, text=row.text, author_id=row.author_id,
                      author_name=ctx.user.full_name, created_at=row.created_at)


@router.get("/tasks/{task_id}/history", response_model=list[HistoryOut])
def history(task_id: int, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    t = _get(db, ctx, task_id)
    rows = db.scalars(select(TaskHistory).where(TaskHistory.task_id == t.id)
                      .order_by(TaskHistory.id)).all()
    names = {u.id: u.full_name for u in db.scalars(
        select(User).where(User.id.in_({r.actor_id for r in rows if r.actor_id} or {0})))}
    return [HistoryOut(id=r.id, action=r.action, actor_id=r.actor_id,
                       actor_name=names.get(r.actor_id, "tizim"),
                       old_values_json=r.old_values_json or {}, new_values_json=r.new_values_json or {},
                       created_at=r.created_at) for r in rows]
