"""Business rules: state machine, progress, code generation, history, notifications."""
from __future__ import annotations

from datetime import datetime, date
from decimal import Decimal
from typing import Optional, Iterable

from sqlalchemy import select, func, text
from sqlalchemy.orm import Session

from ..auth import Ctx
from ..errors import validation, invalid_transition, ApiError, task_not_found
from ..models import (
    Task, TaskChecklistItem, TaskAttachment, TaskDependency, TaskHistory, TaskType, Notification, User,
    TaskDailyProgress, Location, BLOCK_REASONS, TASK_STATUSES, PRIORITIES,
)

TRANSITIONS = {
    "plan": {"progress", "blocked", "cancelled"},
    "progress": {"review", "blocked"},
    "review": {"done", "progress"},
    "done": {"progress"},        # only via reopen
    "blocked": set(),            # only via unblock -> previous_status
    "cancelled": set(),
}


def utcnow():
    return datetime.utcnow()


# ---------- helpers ----------
def code_taken(db: Session, n) -> bool:
    return bool(db.execute(select(func.count()).select_from(Task).where(Task.code == f"V-{n}")).scalar())


def max_code_num(db: Session) -> int:
    """Mavjud eng katta V-<raqam> kodi (0 - hech narsa yo'q)."""
    if db.bind.dialect.name == "postgresql":
        return int(db.execute(text(
            "SELECT COALESCE(MAX(CAST(SUBSTRING(code FROM 3) AS BIGINT)), 0) "
            "FROM tasks WHERE code ~ '^V-[0-9]+$'")).scalar() or 0)
    best = 0
    for (c,) in db.execute(select(Task.code)):
        if c and c.startswith("V-") and c[2:].isdigit():
            best = max(best, int(c[2:]))
    return best


def sync_code_sequence(db: Session) -> int:
    """Postgres ketma-ketligini bazadagi eng katta koddan keyinga suradi.
    Baza tashqaridan to'ldirilganda (fake_data, import, zaxiradan tiklash) ketma-ketlik
    ma'lumotdan orqada qoladi va yangi vazifa yaratishda kod to'qnashadi -> 500."""
    if db.bind.dialect.name != "postgresql":
        return 0
    top = max(1000, max_code_num(db))
    db.execute(text("SELECT setval('task_code_seq', :v)"), {"v": top})
    return top


def next_code(db: Session) -> str:
    """Server-side task code. Postgres uses a sequence (safe under concurrency);
    other dialects (tests) fall back to max(id). Ketma-ketlik ma'lumotdan orqada qolib
    qolgan bo'lsa - o'zi tuzatib oladi."""
    if db.bind.dialect.name == "postgresql":
        n = db.execute(text("SELECT nextval('task_code_seq')")).scalar()
        if code_taken(db, n):
            sync_code_sequence(db)
            n = db.execute(text("SELECT nextval('task_code_seq')")).scalar()
    else:
        n = 1000 + (db.execute(select(func.max(Task.id))).scalar() or 0) + 1
        while code_taken(db, n):
            n += 1
    return f"V-{n}"


def log(db: Session, task: Task, action: str, ctx: Optional[Ctx], old: dict | None = None, new: dict | None = None):
    def clean(d):
        out = {}
        for k, v in (d or {}).items():
            if isinstance(v, (datetime, date)):
                v = v.isoformat()
            elif isinstance(v, Decimal):
                v = float(v)
            out[k] = v
        return out
    db.add(TaskHistory(task_id=task.id, action=action, old_values_json=clean(old), new_values_json=clean(new),
                       actor_id=ctx.user.id if ctx else None, source=ctx.source if ctx else "system",
                       request_id=ctx.request_id if ctx else None))


def notify(db: Session, user_ids: Iterable[int], event: str, task: Task | None, payload: dict | None = None,
           telegram: bool = True, inapp: bool = True):
    payload = dict(payload or {})
    if task:
        payload.setdefault("task_id", task.id)
        payload.setdefault("code", task.code)
        payload.setdefault("title", task.title)
    seen = set()
    for uid in user_ids:
        if not uid or uid in seen:
            continue
        seen.add(uid)
        u = db.get(User, uid)
        if not u or not u.is_active:
            continue
        if inapp:
            db.add(Notification(user_id=uid, task_id=task.id if task else None, event=event,
                                payload_json=payload, channel="inapp", status="sent", sent_at=utcnow()))
        if telegram and u.telegram_user_id:
            db.add(Notification(user_id=uid, task_id=task.id if task else None, event=event,
                                payload_json=payload, channel="telegram", status="pending"))


def recompute_progress(db: Session, task: Task):
    items = db.scalars(select(TaskChecklistItem).where(TaskChecklistItem.task_id == task.id)).all()
    if items:
        done = sum(1 for i in items if i.is_done)
        task.progress_percent = int(round(done / len(items) * 100))
    elif task.planned_quantity and float(task.planned_quantity) > 0:
        task.progress_percent = min(100, int(round(float(task.actual_quantity or 0) / float(task.planned_quantity) * 100)))
    else:
        task.progress_percent = 100 if task.status == "done" else 0
    if task.status == "done":
        task.progress_percent = 100


def recompute_quantity(db: Session, task: Task):
    total = db.execute(
        select(func.coalesce(func.sum(TaskDailyProgress.quantity), 0))
        .where(TaskDailyProgress.task_id == task.id, TaskDailyProgress.is_duplicate == False)  # noqa
    ).scalar()
    task.actual_quantity = total or 0
    task.quantity_over_plan = bool(task.planned_quantity and float(total or 0) > float(task.planned_quantity))
    recompute_progress(db, task)


def bump(task: Task):
    task.row_version += 1
    task.updated_at = utcnow()


def get_task_or_404(db: Session, task_id: int) -> Task:
    t = db.get(Task, task_id)
    if not t or not t.is_active:
        raise task_not_found()
    return t


def type_required_kinds(db: Session, task: Task) -> list:
    tt = db.get(TaskType, task.type_id)
    return list(tt.required_evidence_kinds or []) if tt else []


# ---------- dependency checks ----------
def has_cycle(db: Session, task_id: int, depends_on: int) -> bool:
    """Would adding task_id -> depends_on create a cycle? (i.e. depends_on reaches task_id)"""
    stack = [depends_on]
    seen = set()
    while stack:
        cur = stack.pop()
        if cur == task_id:
            return True
        if cur in seen:
            continue
        seen.add(cur)
        for (d,) in db.execute(select(TaskDependency.depends_on_task_id).where(TaskDependency.task_id == cur)):
            stack.append(d)
    return False


def pending_dependencies(db: Session, task: Task) -> list[Task]:
    deps = db.scalars(
        select(Task).join(TaskDependency, TaskDependency.depends_on_task_id == Task.id)
        .where(TaskDependency.task_id == task.id, Task.status != "done", Task.is_active == True)  # noqa
    ).all()
    return deps


# ---------- state machine ----------
def transition(db: Session, ctx: Ctx, task: Task, to: str, note: Optional[str] = None,
               block_reason: Optional[str] = None):
    frm = task.status
    if to not in TASK_STATUSES:
        raise invalid_transition(frm, to)

    if to == "blocked":
        if frm in ("done", "cancelled", "blocked"):
            raise invalid_transition(frm, to)
        if block_reason not in BLOCK_REASONS or not (note or "").strip():
            raise validation("BLOCK_REASON_REQUIRED", "Bloklash sababi va izohi majburiy.")
        ctx.require("tasks.block")
        old = {"status": frm}
        task.previous_status, task.status = frm, "blocked"
        task.blocked_reason, task.blocked_note, task.blocked_at = block_reason, note, utcnow()
        bump(task)
        log(db, task, "block", ctx, old, {"status": "blocked", "reason": block_reason, "note": note})
        notify(db, prorab_and_rahbar_ids(db, task) | {task.reviewer_id}, "blocked", task,
               {"reason": block_reason, "note": note, "urgent": True})
        return

    if frm == "blocked":
        # unblock: only back to previous_status
        prev = task.previous_status or "plan"
        if to != prev:
            raise invalid_transition(frm, to)
        ctx.require("tasks.block")
        old = {"status": frm}
        task.status, task.previous_status = prev, None
        task.blocked_reason = task.blocked_note = None
        task.blocked_at = None
        bump(task)
        log(db, task, "unblock", ctx, old, {"status": prev})
        return

    if to not in TRANSITIONS.get(frm, set()):
        raise invalid_transition(frm, to)

    if frm == "plan" and to == "progress":
        ctx.require("tasks.start")
        if ctx.user.role.code == "bajaruvchi" and task.assignee_id != ctx.user.id:
            raise ApiError(403, "SCOPE_FORBIDDEN", "Bu vazifa sizga biriktirilmagan.")
        pend = pending_dependencies(db, task)
        if pend:
            raise ApiError(409, "DEPENDENCY_NOT_DONE", "Oldingi bog'liq vazifa hali tugamagan: " + ", ".join(p.code for p in pend),
                           codes=[p.code for p in pend])
        task.status = "progress"
        task.actual_start = task.actual_start or utcnow()
        bump(task)
        log(db, task, "start", ctx, {"status": frm}, {"status": "progress"})
        return

    if frm == "progress" and to == "review":
        ctx.require("tasks.submit_review")
        if ctx.user.role.code == "bajaruvchi" and task.assignee_id != ctx.user.id:
            raise ApiError(403, "SCOPE_FORBIDDEN", "Bu vazifa sizga biriktirilmagan.")
        missing = [i.title for i in db.scalars(select(TaskChecklistItem).where(
            TaskChecklistItem.task_id == task.id, TaskChecklistItem.is_required == True,  # noqa
            TaskChecklistItem.is_done == False)).all()]  # noqa
        if missing:
            raise validation("REQUIRED_CHECKLIST", "Majburiy checklist bandlari bajarilmagan.", items=missing)
        req = type_required_kinds(db, task)
        have = set(k for (k,) in db.execute(select(TaskAttachment.kind).where(
            TaskAttachment.task_id == task.id, TaskAttachment.is_active == True)))  # noqa
        lack = [k for k in req if k not in have]
        if lack:
            raise validation("REQUIRED_EVIDENCE", "Majburiy foto biriktirilmagan.", kinds=lack)
        task.status = "review"
        task.review_started_at = utcnow()
        bump(task)
        log(db, task, "submit_review", ctx, {"status": frm}, {"status": "review"})
        notify(db, [task.reviewer_id], "submitted_review", task, {"urgent": True})
        return

    if frm == "review" and to == "done":
        ctx.require("tasks.accept")
        if task.assignee_id == ctx.user.id:
            raise ApiError(409, "SELF_ACCEPT_FORBIDDEN", "O'zingiz bajargan vazifani o'zingiz qabul qila olmaysiz.")
        if ctx.user.role.code == "tekshiruvchi" and task.reviewer_id != ctx.user.id:
            raise ApiError(403, "SCOPE_FORBIDDEN", "Siz bu vazifaning tekshiruvchisi emassiz.")
        task.status = "done"
        task.actual_end = utcnow()
        task.progress_percent = 100
        bump(task)
        log(db, task, "accept", ctx, {"status": frm}, {"status": "done", "note": note})
        notify(db, [task.assignee_id], "accepted", task)
        return

    if frm == "review" and to == "progress":
        ctx.require("tasks.return")
        if not (note or "").strip():
            raise validation("RETURN_REASON_REQUIRED", "Qaytarish sababini yozing.")
        task.status = "progress"
        task.return_count += 1
        task.review_started_at = None
        bump(task)
        log(db, task, "return", ctx, {"status": frm}, {"status": "progress", "reason": note, "return_count": task.return_count})
        notify(db, [task.assignee_id], "returned", task, {"reason": note, "urgent": True})
        return

    if frm == "done" and to == "progress":
        ctx.require("tasks.reopen")
        task.status = "progress"
        task.actual_end = None
        bump(task)
        log(db, task, "reopen", ctx, {"status": frm}, {"status": "progress", "note": note})
        notify(db, [task.assignee_id, task.reviewer_id], "reopened", task, {"note": note})
        return

    if frm == "plan" and to == "cancelled":
        ctx.require("tasks.delete")
        task.status = "cancelled"
        bump(task)
        log(db, task, "cancel", ctx, {"status": frm}, {"status": "cancelled", "note": note})
        notify(db, [task.assignee_id], "cancelled", task)
        return

    raise invalid_transition(frm, to)


def prorab_and_rahbar_ids(db: Session, task: Task) -> set[int]:
    """Everyone who supervises this task: its prorab (by block), its rahbar (by project),
    the system/project administrators, and whoever created it."""
    ids = set()
    users = db.scalars(select(User).where(User.is_active == True)).all()  # noqa
    from ..auth import location_in_scope
    for u in users:
        code = u.role.code
        if code in ("admin", "rahbar"):
            if u.scope_type == "system" or (u.scope_type == "project" and u.scope_id == task.project_id):
                ids.add(u.id)
        elif code == "prorab":
            from ..auth import scope_project_id
            in_block = u.scope_type == "location" and location_in_scope(db, task.location_id, u.scope_id)
            # joysiz (butun obyekt bo'yicha) vazifa - o'sha loyihaning barcha prorablariga tegishli
            project_wide = (u.scope_type == "location" and task.location_id is None
                            and scope_project_id(db, u) == task.project_id)
            if u.scope_type == "system" or (u.scope_type == "project" and u.scope_id == task.project_id) \
               or in_block or project_wide:
                ids.add(u.id)
    ids.add(task.created_by)
    return ids


# kept as the readable alias used by newer code
supervisor_ids = prorab_and_rahbar_ids


# ---------- permissions object for UI ----------
def task_permissions(db: Session, ctx: Ctx, task: Task) -> dict:
    u = ctx.user
    role = u.role.code
    p = ctx.perms
    mine = task.assignee_id == u.id
    is_reviewer = task.reviewer_id == u.id
    st = task.status
    can_actor = (role != "bajaruvchi") or mine
    return {
        "edit": "tasks.edit" in p and st not in ("done", "cancelled"),
        "change_dates": "tasks.change_dates" in p,
        "assign": "tasks.assign" in p,
        "start": "tasks.start" in p and st == "plan" and can_actor,
        "submit_review": "tasks.submit_review" in p and st == "progress" and can_actor,
        "accept": "tasks.accept" in p and st == "review" and not mine and (role != "tekshiruvchi" or is_reviewer),
        "return": "tasks.return" in p and st == "review" and (role != "tekshiruvchi" or is_reviewer),
        "block": "tasks.block" in p and st in ("plan", "progress", "review") and can_actor,
        "unblock": "tasks.block" in p and st == "blocked",
        "reopen": "tasks.reopen" in p and st == "done",
        "cancel": "tasks.delete" in p and st == "plan",
        "delete": "tasks.delete" in p and st != "done",
        "checklist": "checklist.edit" in p and st in ("plan", "progress", "review") and can_actor,
        "progress": "progress.create" in p and st in ("progress", "blocked") and can_actor,
        "upload": "attachments.upload" in p and st not in ("done", "cancelled") and can_actor,
        "delete_attachment": "attachments.delete" in p and st != "done",
        "comment": "comments.create" in p,
    }
