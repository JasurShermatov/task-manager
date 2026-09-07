"""Turn Task rows into TaskCard/TaskDetail dicts with denormalized fields (one query per collection)."""
from __future__ import annotations

from datetime import date, datetime
from typing import Iterable

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from ..models import (Task, User, TaskType, Project, Location, TaskChecklistItem, TaskAttachment,
                      TaskDependency)
from ..schemas import TaskCard, LocationPath
from .files import signed_url


def _days(a: datetime | date | None, b: datetime | date | None) -> int:
    if not a or not b:
        return 0
    if isinstance(a, datetime):
        a = a.date()
    if isinstance(b, datetime):
        b = b.date()
    return (b - a).days


def location_path(db: Session, loc_id: int | None, cache: dict) -> list[LocationPath]:
    path = []
    cur_id = loc_id
    guard = 0
    while cur_id and guard < 10:
        guard += 1
        loc = cache.get(cur_id)
        if loc is None:
            loc = db.get(Location, cur_id)
            cache[cur_id] = loc
        if not loc:
            break
        path.append(LocationPath(id=loc.id, name=loc.name, kind=loc.kind))
        cur_id = loc.parent_id
    return list(reversed(path))


def build_cards(db: Session, tasks: list[Task], today: date | None = None) -> list[TaskCard]:
    if not tasks:
        return []
    today = today or date.today()
    ids = [t.id for t in tasks]
    user_ids = {t.assignee_id for t in tasks} | {t.reviewer_id for t in tasks}
    users = {u.id: u for u in db.scalars(select(User).where(User.id.in_(user_ids))).all()}
    types = {tt.id: tt for tt in db.scalars(select(TaskType)).all()}
    projects = {p.id: p for p in db.scalars(select(Project)).all()}

    ck = {}
    for tid, total, done in db.execute(
        select(TaskChecklistItem.task_id, func.count(), func.sum(func.cast(TaskChecklistItem.is_done, __import__("sqlalchemy").Integer)))
        .where(TaskChecklistItem.task_id.in_(ids)).group_by(TaskChecklistItem.task_id)
    ):
        ck[tid] = (int(done or 0), int(total))
    photos = {tid: int(n) for tid, n in db.execute(
        select(TaskAttachment.task_id, func.count()).where(
            TaskAttachment.task_id.in_(ids), TaskAttachment.is_active == True,  # noqa
            TaskAttachment.kind != "document").group_by(TaskAttachment.task_id))}
    deps_pending: dict[int, list[str]] = {}
    for tid, code in db.execute(
        select(TaskDependency.task_id, Task.code).join(Task, Task.id == TaskDependency.depends_on_task_id)
        .where(TaskDependency.task_id.in_(ids), Task.status != "done")
    ):
        deps_pending.setdefault(tid, []).append(code)

    loc_cache: dict = {}
    now = datetime.utcnow()
    out = []
    for t in tasks:
        c = TaskCard.model_validate(t)
        c.assignee_name = users[t.assignee_id].full_name if t.assignee_id in users else ""
        c.reviewer_name = users[t.reviewer_id].full_name if t.reviewer_id in users else ""
        c.type_name = types[t.type_id].name if t.type_id in types else ""
        c.project_name = projects[t.project_id].name if t.project_id in projects else ""
        c.location_path = location_path(db, t.location_id, loc_cache)
        c.checklist_done, c.checklist_total = ck.get(t.id, (0, 0))
        c.photos_count = photos.get(t.id, 0)
        c.overdue_days = max(0, _days(t.planned_end, today)) if t.status not in ("done", "cancelled") and t.planned_end < today else 0
        c.review_days = max(0, _days(t.review_started_at, now)) if t.status == "review" and t.review_started_at else 0
        c.blocked_days = max(0, _days(t.blocked_at, now)) if t.status == "blocked" and t.blocked_at else 0
        c.dependency_pending = deps_pending.get(t.id, [])
        out.append(c)
    return out


def attachment_out(db: Session, a: TaskAttachment, users: dict | None = None):
    from ..schemas import AttachmentOut
    o = AttachmentOut.model_validate(a)
    o.url = signed_url(a.id)
    if users is not None and a.uploaded_by in users:
        o.uploaded_by_name = users[a.uploaded_by].full_name
    else:
        u = db.get(User, a.uploaded_by)
        o.uploaded_by_name = u.full_name if u else ""
    return o
