from __future__ import annotations

from datetime import timedelta, date
from typing import List, Optional

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import Ctx, get_ctx, check_project_scope
from ..db import get_db
from ..errors import validation, not_found, ApiError
from ..models import TaskTemplate, TaskType, Task, Location, TaskChecklistItem, TaskDependency, Job, TaskRecurringRule, User
from ..schemas import (TemplateOut, TemplateIn, InstantiateIn, TaskDetail, TaskCreate, BulkCopyIn, RecurringOut, RecurringIn)
from ..services import tasks as svc
from .tasks import create_task_core, get_detail

router = APIRouter(tags=["templates"])


def _apply(obj, data):
    for k, v in data.items():
        setattr(obj, k, v)


@router.get("/task-templates", response_model=List[TemplateOut])
def templates(ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db), include_inactive: bool = False):
    q = select(TaskTemplate).order_by(TaskTemplate.name)
    if not include_inactive:
        q = q.where(TaskTemplate.is_active == True)  # noqa
    return db.scalars(q).all()


@router.post("/task-templates", response_model=TemplateOut, status_code=201)
def template_create(body: TemplateIn, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    ctx.require("admin.templates")
    if not body.name or not body.type_id or not body.title_pattern:
        raise validation("VALIDATION", "Nom, ish turi va sarlavha shabloni majburiy.")
    tt = db.get(TaskType, body.type_id) or (_ for _ in ()).throw(not_found("Ish turi"))
    t = TaskTemplate(name=body.name, type_id=body.type_id, title_pattern=body.title_pattern,
                     default_duration_days=body.default_duration_days or tt.default_duration_days,
                     checklist_json=body.checklist_json if body.checklist_json is not None else tt.default_checklist_json,
                     required_evidence_kinds=body.required_evidence_kinds if body.required_evidence_kinds is not None else tt.required_evidence_kinds)
    db.add(t)
    db.commit()
    return t


@router.patch("/task-templates/{tid}", response_model=TemplateOut)
def template_patch(tid: int, body: TemplateIn, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    ctx.require("admin.templates")
    t = db.get(TaskTemplate, tid) or (_ for _ in ()).throw(not_found("Shablon"))
    _apply(t, body.model_dump(exclude_unset=True))
    db.commit()
    return t


def render_title(pattern: str, variables: dict, loc: Optional[Location]) -> str:
    v = dict(variables or {})
    if loc:
        v.setdefault("joy", loc.name)
        v.setdefault("location", loc.name)
    out = pattern
    for k, val in v.items():
        out = out.replace("{" + k + "}", str(val))
    return out


@router.post("/task-templates/{tid}/instantiate", response_model=TaskDetail, status_code=201)
def instantiate(tid: int, body: InstantiateIn, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    tpl = db.get(TaskTemplate, tid) or (_ for _ in ()).throw(not_found("Shablon"))
    loc = db.get(Location, body.location_id) if body.location_id else None
    tc = TaskCreate(project_id=body.project_id, location_id=body.location_id, type_id=tpl.type_id,
                    title=render_title(tpl.title_pattern, body.variables, loc), priority=body.priority,
                    assignee_id=body.assignee_id, reviewer_id=body.reviewer_id, planned_start=body.planned_start,
                    planned_end=body.planned_start + timedelta(days=max(0, tpl.default_duration_days - 1)),
                    checklist=tpl.checklist_json or [], template_id=tpl.id)
    task = create_task_core(db, ctx, tc)
    db.commit()
    return get_detail(db, ctx, task)


# ---------- bulk copy ----------
@router.post("/tasks/bulk-copy")
def bulk_copy(body: BulkCopyIn, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    ctx.require("tasks.bulk_create")
    src = db.get(Location, body.source_location_id) or (_ for _ in ()).throw(not_found("Manba joy"))
    check_project_scope(ctx, src.project_id, src.id, db)
    source_tasks = db.scalars(select(Task).where(Task.location_id == body.source_location_id, Task.is_active == True,  # noqa
                                                 Task.status != "cancelled").order_by(Task.planned_start, Task.id)).all()
    targets = [db.get(Location, i) for i in body.target_location_ids]
    if any(t is None or t.project_id != src.project_id for t in targets):
        raise validation("VALIDATION", "Maqsad joylar noto'g'ri.")
    total = len(source_tasks) * len(targets)
    if total > 1000:
        raise validation("BULK_LIMIT", "Bir marta 1000 tadan ko'p vazifa yaratib bo'lmaydi.", total=total)
    preview = []
    for ti, tgt in enumerate(targets, start=1):
        shift = timedelta(days=body.date_step_days * ti)
        for s in source_tasks:
            preview.append({"target_location_id": tgt.id, "target_location": tgt.name, "source_code": s.code,
                            "title": s.title.replace(src.name, tgt.name),
                            "planned_start": str(s.planned_start + shift), "planned_end": str(s.planned_end + shift),
                            "assignee_id": s.assignee_id if body.assignee_policy == "keep" else int(body.assignee_policy.split(":")[1])})
    if body.dry_run:
        return {"dry_run": True, "total": total, "date_range": [min((p["planned_start"] for p in preview), default=None),
                                                                  max((p["planned_end"] for p in preview), default=None)],
                "items": preview}

    job = Job(kind="bulk_copy", status="running", total=total, created_by=ctx.user.id)
    db.add(job)
    db.flush()
    created = []
    for ti, tgt in enumerate(targets, start=1):
        shift = timedelta(days=body.date_step_days * ti)
        id_map = {}
        added_deps: set[tuple[int, int]] = set()
        for s in source_tasks:
            assignee = s.assignee_id if body.assignee_policy == "keep" else int(body.assignee_policy.split(":")[1])
            checklist = [{"title": c.title, "is_required": c.is_required} for c in
                         db.scalars(select(TaskChecklistItem).where(TaskChecklistItem.task_id == s.id).order_by(TaskChecklistItem.sort_order))]
            tc = TaskCreate(project_id=s.project_id, location_id=tgt.id, type_id=s.type_id,
                            title=s.title.replace(src.name, tgt.name), description=s.description, priority=s.priority,
                            assignee_id=assignee, reviewer_id=s.reviewer_id, planned_start=s.planned_start + shift,
                            planned_end=s.planned_end + shift, planned_quantity=s.planned_quantity, unit=s.unit,
                            planned_crew_size=s.planned_crew_size, checklist=checklist, template_id=s.template_id)
            nt = create_task_core(db, ctx, tc)
            id_map[s.id] = nt.id
            created.append(nt.code)
            job.done += 1
        # copy dependencies inside the same floor
        for s in source_tasks:
            for (dep,) in db.execute(select(TaskDependency.depends_on_task_id).where(TaskDependency.task_id == s.id)):
                if dep in id_map:
                    pair = (id_map[s.id], id_map[dep])
                    if pair not in added_deps:
                        added_deps.add(pair)
                        db.add(TaskDependency(task_id=pair[0], depends_on_task_id=pair[1]))
        if body.dependency_policy == "chain":
            ordered = [id_map[s.id] for s in source_tasks]
            for a, b in zip(ordered, ordered[1:]):
                if (b, a) not in added_deps:
                    added_deps.add((b, a))
                    db.add(TaskDependency(task_id=b, depends_on_task_id=a))
        db.flush()
    job.status = "done"
    job.result_json = {"created": created}
    db.commit()
    return {"dry_run": False, "job_id": job.id, "total": total, "created": created}


@router.get("/jobs/{jid}")
def job(jid: int, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    j = db.get(Job, jid) or (_ for _ in ()).throw(not_found("Job"))
    return {"id": j.id, "kind": j.kind, "status": j.status, "total": j.total, "done": j.done, "result": j.result_json}


# ---------- recurring ----------
@router.get("/task-recurring-rules", response_model=List[RecurringOut])
def rules(ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    ctx.require("tasks.bulk_create")
    return db.scalars(select(TaskRecurringRule).order_by(TaskRecurringRule.id)).all()


@router.post("/task-recurring-rules", response_model=RecurringOut, status_code=201)
def rule_create(body: RecurringIn, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    ctx.require("tasks.bulk_create")
    if not (body.template_id and body.project_id and body.assignee_id and body.reviewer_id and body.rrule):
        raise validation("VALIDATION", "Shablon, loyiha, mas'ul, tekshiruvchi va qoida majburiy.")
    if not (body.rrule.startswith("FREQ=DAILY") or body.rrule.startswith("FREQ=WEEKLY")):
        raise validation("VALIDATION", "Qoida FREQ=DAILY yoki FREQ=WEEKLY;BYDAY=MO,WE bo'lishi kerak.")
    r = TaskRecurringRule(template_id=body.template_id, project_id=body.project_id, location_id=body.location_id,
                          assignee_id=body.assignee_id, reviewer_id=body.reviewer_id, rrule=body.rrule,
                          next_run_at=date.today() + timedelta(days=1))
    db.add(r)
    db.commit()
    return r


@router.patch("/task-recurring-rules/{rid}", response_model=RecurringOut)
def rule_patch(rid: int, body: RecurringIn, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    ctx.require("tasks.bulk_create")
    r = db.get(TaskRecurringRule, rid) or (_ for _ in ()).throw(not_found("Qoida"))
    _apply(r, body.model_dump(exclude_unset=True))
    db.commit()
    return r
