from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, or_
from sqlalchemy.orm import Session

from ..auth import Ctx, get_ctx, hash_password, validate_password_strength, user_in_project
from ..db import get_db
from ..errors import validation, not_found, permission_denied
from ..models import Project, Location, TaskType, User, Role, Task, TaskHistory
from ..permissions import ALL_PERMS, PERM_GROUPS
from ..schemas import (ProjectOut, ProjectIn, LocationOut, LocationIn, TaskTypeOut, TaskTypeIn, UserOut, UserCreate,
                       UserPatch, RoleOut, RoleIn, UserBrief)
from ..services import tasks as svc

router = APIRouter(tags=["admin"])


def _apply(obj, data: dict):
    for k, v in data.items():
        setattr(obj, k, v)


# ---------- projects ----------
@router.get("/projects", response_model=List[ProjectOut])
def projects(ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db), include_inactive: bool = False):
    q = select(Project).order_by(Project.name)
    if not include_inactive:
        q = q.where(Project.is_active == True)  # noqa
    rows = db.scalars(q).all()
    rows = [p for p in rows if user_in_project(ctx.user, p.id, db)]
    if ctx.user.role.code == "bajaruvchi":
        # bajaruvchi doirasi - o'ziga biriktirilgan ish, shuning uchun faqat o'zi ishlaydigan obyektlar
        mine = set(db.scalars(select(Task.project_id).where(
            or_(Task.assignee_id == ctx.user.id, Task.reviewer_id == ctx.user.id), Task.is_active == True)))  # noqa
        rows = [p for p in rows if p.id in mine]
    return rows


@router.get("/projects/stats")
def project_stats(ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    """Har loyiha bo'yicha qisqa raqamlar (ro'yxatda ko'rsatish uchun)."""
    from datetime import date as _date
    from .tasks import scope_filter
    today = _date.today()
    q = scope_filter(ctx, db, select(Task).where(Task.is_active == True))  # noqa
    out: dict[int, dict] = {}
    for t in db.scalars(q):
        row = out.setdefault(t.project_id, {"total": 0, "open": 0, "overdue": 0, "done": 0})
        row["total"] += 1
        if t.status in ("plan", "progress", "review", "blocked"):
            row["open"] += 1
            if t.planned_end < today:
                row["overdue"] += 1
        elif t.status == "done":
            row["done"] += 1
    return out


@router.post("/projects", response_model=ProjectOut, status_code=201)
def project_create(body: ProjectIn, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    ctx.require("admin.projects")
    if not body.code or not body.name:
        raise validation("VALIDATION", "Kod va nom majburiy.")
    if db.scalar(select(Project).where(Project.code == body.code)):
        raise validation("VALIDATION", "Bu kod band.", field_errors={"code": "exists"})
    p = Project(code=body.code.strip().upper(), name=body.name.strip())
    db.add(p)
    db.commit()
    return p


@router.patch("/projects/{pid}", response_model=ProjectOut)
def project_patch(pid: int, body: ProjectIn, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    ctx.require("admin.projects")
    p = db.get(Project, pid) or (_ for _ in ()).throw(not_found("Loyiha"))
    _apply(p, body.model_dump(exclude_unset=True))
    db.commit()
    return p


# ---------- locations ----------
@router.get("/locations", response_model=List[LocationOut])
def locations(project_id: Optional[int] = None, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    q = select(Location).where(Location.is_active == True).order_by(Location.sort_order, Location.name)  # noqa
    if project_id:
        q = q.where(Location.project_id == project_id)
    return db.scalars(q).all()


@router.post("/locations", response_model=LocationOut, status_code=201)
def location_create(body: LocationIn, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    ctx.require("admin.projects")
    if not body.project_id or not body.name or body.kind not in ("block", "floor", "zone"):
        raise validation("VALIDATION", "Loyiha, nom va tur majburiy.")
    if body.parent_id:
        par = db.get(Location, body.parent_id)
        if not par or par.project_id != body.project_id:
            raise validation("VALIDATION", "Ota joy noto'g'ri.", field_errors={"parent_id": "invalid"})
    loc = Location(project_id=body.project_id, parent_id=body.parent_id, name=body.name.strip(), kind=body.kind,
                   sort_order=body.sort_order or 0)
    db.add(loc)
    db.commit()
    return loc


@router.patch("/locations/{lid}", response_model=LocationOut)
def location_patch(lid: int, body: LocationIn, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    ctx.require("admin.projects")
    loc = db.get(Location, lid) or (_ for _ in ()).throw(not_found("Joy"))
    _apply(loc, body.model_dump(exclude_unset=True, exclude={"project_id"}))
    db.commit()
    return loc


# ---------- task types ----------
@router.get("/task-types", response_model=List[TaskTypeOut])
def task_types(ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db), include_inactive: bool = False):
    q = select(TaskType).order_by(TaskType.group_name, TaskType.name)
    if not include_inactive:
        q = q.where(TaskType.is_active == True)  # noqa
    return db.scalars(q).all()


@router.post("/task-types", response_model=TaskTypeOut, status_code=201)
def task_type_create(body: TaskTypeIn, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    ctx.require("admin.task_types")
    if not body.name:
        raise validation("VALIDATION", "Nom majburiy.", field_errors={"name": "required"})
    tt = TaskType(name=body.name.strip(), group_name=body.group_name, default_duration_days=body.default_duration_days or 3,
                  required_evidence_kinds=body.required_evidence_kinds or [], default_checklist_json=body.default_checklist_json or [])
    db.add(tt)
    db.commit()
    return tt


@router.patch("/task-types/{tid}", response_model=TaskTypeOut)
def task_type_patch(tid: int, body: TaskTypeIn, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    ctx.require("admin.task_types")
    tt = db.get(TaskType, tid) or (_ for _ in ()).throw(not_found("Ish turi"))
    _apply(tt, body.model_dump(exclude_unset=True))
    db.commit()
    return tt


# ---------- roles ----------
@router.get("/roles", response_model=List[RoleOut])
def roles(ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    return db.scalars(select(Role).order_by(Role.id)).all()


@router.get("/roles/permissions", response_model=List[str])
def perm_catalog(ctx: Ctx = Depends(get_ctx)):
    return ALL_PERMS


@router.get("/roles/permission-groups")
def perm_groups(ctx: Ctx = Depends(get_ctx)):
    """UI ruxsatlarni guruhlab ko'rsatishi uchun."""
    return [{"group": g, "permissions": items} for g, items in PERM_GROUPS]


@router.patch("/roles/{rid}", response_model=RoleOut)
def role_patch(rid: int, body: RoleIn, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    ctx.require("admin.roles")
    r = db.get(Role, rid) or (_ for _ in ()).throw(not_found("Rol"))
    if r.code == "admin":
        raise validation("VALIDATION", "Administrator roli o'zgartirilmaydi.")
    data = body.model_dump(exclude_unset=True, exclude={"code"})
    if "permissions_json" in data:
        bad = [p for p in data["permissions_json"] if p not in ALL_PERMS]
        if bad:
            raise validation("VALIDATION", f"Noma'lum ruxsat: {bad}")
    _apply(r, data)
    db.commit()
    return r


@router.post("/roles", response_model=RoleOut, status_code=201)
def role_create(body: RoleIn, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    ctx.require("admin.roles")
    if not body.code or not body.name:
        raise validation("VALIDATION", "Kod va nom majburiy.")
    r = Role(code=body.code.strip().lower(), name=body.name, permissions_json=body.permissions_json or [], is_system=False)
    db.add(r)
    db.commit()
    return r


# ---------- users ----------
@router.get("/users", response_model=List[UserOut])
def users(ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db),
          q: Optional[str] = None, role: Optional[str] = None, project_id: Optional[int] = None,
          include_inactive: bool = False):
    stmt = select(User).order_by(User.full_name)
    if not include_inactive:
        stmt = stmt.where(User.is_active == True)  # noqa
    if q:
        stmt = stmt.where(or_(User.full_name.ilike(f"%{q}%"), User.login.ilike(f"%{q}%")))
    rows = db.scalars(stmt).all()
    if role:
        rows = [u for u in rows if u.role.code in role.split(",")]
    if project_id:
        rows = [u for u in rows if user_in_project(u, project_id, db)]
    if not ctx.has("admin.users"):
        # non-admins get a slim view but same schema (hide contacts)
        for u in rows:
            u.phone = None
            u.email = None
    return rows


@router.post("/users", response_model=UserOut, status_code=201)
def user_create(body: UserCreate, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    ctx.require("admin.users")
    if db.scalar(select(User).where(User.login == body.login)):
        raise validation("VALIDATION", "Bu login band.", field_errors={"login": "exists"})
    validate_password_strength(body.password)
    if not db.get(Role, body.role_id):
        raise validation("VALIDATION", "Rol topilmadi.", field_errors={"role_id": "not_found"})
    if body.scope_type not in ("system", "project", "location"):
        raise validation("VALIDATION", "Doira noto'g'ri.", field_errors={"scope_type": "invalid"})
    if body.scope_type != "system" and not body.scope_id:
        raise validation("VALIDATION", "Doira uchun loyiha/joy tanlanishi kerak.", field_errors={"scope_id": "required"})
    u = User(full_name=body.full_name.strip(), login=body.login.strip(), phone=body.phone, email=body.email,
             password_hash=hash_password(body.password), role_id=body.role_id, scope_type=body.scope_type,
             scope_id=body.scope_id, lang=body.lang if body.lang in ("uz", "ru", "en") else "uz")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@router.patch("/users/{uid}", response_model=UserOut)
def user_patch(uid: int, body: UserPatch, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    u = db.get(User, uid) or (_ for _ in ()).throw(not_found("Foydalanuvchi"))
    data = body.model_dump(exclude_unset=True)
    if uid == ctx.user.id and not ctx.has("admin.users"):
        # self-service: only lang & password & phone
        data = {k: v for k, v in data.items() if k in ("lang", "password", "phone", "full_name")}
    elif not ctx.has("admin.users"):
        raise permission_denied()
    if "password" in data:
        validate_password_strength(data["password"])
        u.password_hash = hash_password(data.pop("password"))
    if "is_active" in data and data["is_active"] is False:
        return block_user(uid, ctx, db)
    _apply(u, data)
    db.commit()
    db.refresh(u)
    return u


@router.post("/users/{uid}/block", response_model=UserOut)
def block_user(uid: int, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    """Soft block: user can't log in, tasks stay; review-queue tasks go to a rahbar."""
    ctx.require("admin.users")
    u = db.get(User, uid) or (_ for _ in ()).throw(not_found("Foydalanuvchi"))
    if u.id == ctx.user.id:
        raise validation("VALIDATION", "O'zingizni bloklay olmaysiz.")
    u.is_active = False
    # re-route review queue
    rahbar = db.scalar(select(User).join(Role).where(Role.code.in_(("rahbar", "admin")), User.is_active == True, User.id != u.id))  # noqa
    if rahbar:
        for t in db.scalars(select(Task).where(Task.reviewer_id == u.id, Task.status.in_(("plan", "progress", "review", "blocked")), Task.is_active == True)):  # noqa
            old = t.reviewer_id
            t.reviewer_id = rahbar.id
            svc.bump(t)
            svc.log(db, t, "reviewer_reassigned", ctx, {"reviewer_id": old}, {"reviewer_id": rahbar.id, "reason": "user_blocked"})
    db.commit()
    db.refresh(u)
    return u


@router.post("/users/{uid}/unblock", response_model=UserOut)
def unblock_user(uid: int, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    ctx.require("admin.users")
    u = db.get(User, uid) or (_ for _ in ()).throw(not_found("Foydalanuvchi"))
    u.is_active = True
    db.commit()
    db.refresh(u)
    return u
