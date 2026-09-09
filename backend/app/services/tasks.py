"""Vazifa domeni: kod berish, tarix, xabar navbati va ro'yxatni boyitish."""
from __future__ import annotations

from datetime import datetime
from typing import Iterable, Optional

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import clock
from ..auth import Ctx
from ..models import (
    CANCELLED, DONE, MANAGERS, NEW, PROGRESS, SUBMITTED, Department, Notification, Task,
    TaskComment, TaskFile, TaskHistory, User,
)
from ..roles import role_name

# ---------------------------------------------------------------- vazifa kodi
# Postgres'da ketma-ketlik, SQLite'da max(id). 1.0 da shu joyda prodda 500 chiqqan edi:
# fake_data satrlarni to'g'ridan-to'g'ri yozgani uchun ketma-ketlik orqada qolib,
# ikkinchi vazifada UNIQUE buzilgan. Shuning uchun next_code o'zini o'zi tuzatadi.


def code_taken(db: Session, n: int) -> bool:
    return bool(db.execute(select(func.count()).select_from(Task).where(Task.code == f"V-{n}")).scalar())


def max_code_num(db: Session) -> int:
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
    if db.bind.dialect.name != "postgresql":
        return 0
    top = max(1000, max_code_num(db))
    db.execute(text("SELECT setval('task_code_seq', :v)"), {"v": top})
    return top


def next_code(db: Session) -> str:
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


# ---------------------------------------------------------------- tarix va xabarlar
def log(db: Session, task: Task, action: str, ctx: Optional[Ctx] = None,
        old: Optional[dict] = None, new: Optional[dict] = None):
    db.add(TaskHistory(task_id=task.id, action=action,
                       old_values_json=old or {}, new_values_json=new or {},
                       actor_id=ctx.user.id if ctx else None,
                       source=ctx.source if ctx else "system"))


def notify(db: Session, user_id: Optional[int], event: str, task: Optional[Task] = None,
           payload: Optional[dict] = None, dedupe_key: Optional[str] = None) -> bool:
    """Telegram navbatiga qo'shadi. `dedupe_key` berilsa, o'sha kalit bilan ikkinchi marta
    yozilmaydi — eslatma dvigateli shunga tayanadi (tekshiruv bazada, kodda emas)."""
    if not user_id:
        return False
    row = Notification(user_id=user_id, task_id=task.id if task else None, event=event,
                       payload_json=payload or {}, channel="telegram", dedupe_key=dedupe_key)
    try:
        with db.begin_nested():
            db.add(row)
        return True
    except IntegrityError:
        return False


def managers(db: Session, exclude: Optional[int] = None) -> list[User]:
    q = select(User).where(User.role.in_(MANAGERS), User.is_active.is_(True))
    return [u for u in db.scalars(q) if u.id != exclude]


def task_payload(db: Session, task: Task, **extra) -> dict:
    a = db.get(User, task.assignee_id)
    dep = db.get(Department, a.department_id) if a and a.department_id else None
    late = task.late_seconds(clock.now())
    return {
        "id": task.id, "code": task.code, "title": task.title,
        "assignee_name": a.full_name if a else "", "assignee_id": task.assignee_id,
        "department": dep.name if dep else None,
        "due_at": task.due_at.isoformat(timespec="minutes"),
        "status": task.status, "late_hours": late // 3600, "late_days": late // 86400,
        **extra,
    }


def notify_managers(db: Session, event: str, task: Task, exclude: Optional[int] = None, **extra):
    payload = task_payload(db, task, **extra)
    for m in managers(db, exclude=exclude):
        notify(db, m.id, event, task, payload)


# ---------------------------------------------------------------- ruxsatlar (UI uchun)
def task_perms(ctx: Ctx, task: Task) -> dict:
    mine = task.assignee_id == ctx.user.id
    mgr = ctx.is_manager
    open_ = task.status in (NEW, PROGRESS)
    return {
        "start": mine and task.status == NEW,
        "submit": mine and open_,
        # o'z ishini o'zi qabul qilmaydi (o'ziga o'zi qo'ygani bundan mustasno)
        "accept": mgr and task.status == SUBMITTED and (not mine or task.created_by == ctx.user.id),
        "return": mgr and task.status == SUBMITTED and (not mine or task.created_by == ctx.user.id),
        "edit": mgr and task.status not in (DONE, CANCELLED),
        "cancel": mgr and task.status not in (DONE, CANCELLED),
        "comment": True,
        "upload": mine or mgr,
    }


# ---------------------------------------------------------------- ro'yxatni boyitish
def enrich(db: Session, tasks: list[Task], ctx: Ctx, *, detail: bool = False) -> list[dict]:
    """Bitta so'rovda hamma ismni yig'ib chiqadi — N+1 bo'lmasin."""
    if not tasks:
        return []
    ref = clock.now()
    ids = {t.id for t in tasks}
    uids = {t.assignee_id for t in tasks} | {t.created_by for t in tasks}
    uids |= {t.accepted_by for t in tasks if t.accepted_by}
    users = {u.id: u for u in db.scalars(select(User).where(User.id.in_(uids)))}
    deps = {d.id: d for d in db.scalars(select(Department))}

    proofs: dict[int, int] = {}
    for tid, n in db.execute(
            select(TaskFile.task_id, func.count()).where(
                TaskFile.task_id.in_(ids), TaskFile.is_active.is_(True), TaskFile.kind == "proof"
            ).group_by(TaskFile.task_id)):
        proofs[tid] = n
    comments: dict[int, int] = {}
    for tid, n in db.execute(
            select(TaskComment.task_id, func.count()).where(TaskComment.task_id.in_(ids))
            .group_by(TaskComment.task_id)):
        comments[tid] = n

    out = []
    for t in tasks:
        a = users.get(t.assignee_id)
        dep = deps.get(a.department_id) if a and a.department_id else None
        late = t.late_seconds(ref)
        row = {
            "id": t.id, "code": t.code, "title": t.title, "description": t.description,
            "status": t.status,
            "assignee_id": t.assignee_id,
            "assignee_name": a.full_name if a else "—",
            "assignee_role": a.role if a else "",
            "department_id": dep.id if dep else None,
            "department_name": dep.name if dep else None,
            "created_by": t.created_by,
            "created_by_name": users[t.created_by].full_name if t.created_by in users else "—",
            "due_at": t.due_at, "original_due_at": t.original_due_at,
            "started_at": t.started_at, "submitted_at": t.submitted_at, "submit_note": t.submit_note,
            "done_at": t.done_at, "accepted_by": t.accepted_by,
            "accepted_by_name": users[t.accepted_by].full_name if t.accepted_by in users else None,
            "return_count": t.return_count, "due_changed_count": t.due_changed_count,
            "row_version": t.row_version, "created_at": t.created_at,
            # ochiq vazifa uchun "hozir kechikkan", bajarilgani uchun "kechikib topshirilgan"
            "is_late": late > 0,
            "late_days": late // 86400, "late_hours": late // 3600,
            "proof_count": proofs.get(t.id, 0), "comment_count": comments.get(t.id, 0),
            "permissions": task_perms(ctx, t),
            "files": [], "comments": [],
        }
        out.append(row)
    return out


def with_files(db: Session, row: dict, task: Task) -> dict:
    from .files import signed_url
    files = db.scalars(select(TaskFile).where(TaskFile.task_id == task.id, TaskFile.is_active.is_(True))
                       .order_by(TaskFile.id)).all()
    row["files"] = [{"id": f.id, "kind": f.kind, "filename": f.filename, "mime_type": f.mime_type,
                     "size": f.size, "url": signed_url(f.id), "created_at": f.created_at} for f in files]
    cs = db.scalars(select(TaskComment).where(TaskComment.task_id == task.id)
                    .order_by(TaskComment.id)).all()
    names = {u.id: u.full_name for u in db.scalars(
        select(User).where(User.id.in_({c.author_id for c in cs} or {0})))}
    row["comments"] = [{"id": c.id, "text": c.text, "author_id": c.author_id,
                        "author_name": names.get(c.author_id, "—"), "created_at": c.created_at} for c in cs]
    return row


def user_out(db: Session, u: User, lang: str = "uz", counts: Optional[dict] = None) -> dict:
    counts = counts or {}
    return {
        "id": u.id, "full_name": u.full_name, "login": u.login, "role": u.role,
        "role_name": role_name(u.role, lang), "position": u.position, "phone": u.phone,
        "department_id": u.department_id,
        "department_name": u.department.name if u.department else None,
        "lang": u.lang, "telegram_user_id": u.telegram_user_id, "is_active": u.is_active,
        "open_tasks": counts.get("open", 0), "late_tasks": counts.get("late", 0),
    }


def task_counts(db: Session, user_ids: Iterable[int]) -> dict[int, dict]:
    """Har bir odam uchun ochiq va kechikkan vazifalar soni."""
    ids = list(user_ids)
    if not ids:
        return {}
    ref = clock.now()
    out: dict[int, dict] = {i: {"open": 0, "late": 0} for i in ids}
    rows = db.execute(
        select(Task.assignee_id, Task.status, Task.due_at)
        .where(Task.assignee_id.in_(ids), Task.status.in_((NEW, PROGRESS, SUBMITTED))))
    for aid, status, due in rows:
        out[aid]["open"] += 1
        if status in (NEW, PROGRESS) and due < ref:
            out[aid]["late"] += 1
    return out
