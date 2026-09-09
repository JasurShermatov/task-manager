"""Administratsiya — faqat boss va assistant.

Uchta alohida ro'yxat, chunki ular uch xil ish:
  * `/departments` + `/users?role=bolim_boshligi`  -> "Bo'limlar" oynasi
  * `/users?role=ijrochi`                          -> "Asosiy bo'lim xodimlari" oynasi
  * `/users?role=assistant`                        -> "Assistantlar" oynasi (faqat boshliqqa)

Boss va assistant kundalik ishda huquqda teng. Yagona farq shu faylda: **assistant
hisoblarini faqat boshliq boshqaradi**. Aks holda assistant o'ziga yana bir assistant
ochib yoki boshliqni bloklab, tepadagi qatlamni o'zi to'ldirib olardi.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth import Ctx, get_ctx, hash_password, validate_password_strength
from ..db import get_db
from ..errors import not_found, validation
from ..models import (
    BOSS, HEAD, MANAGERS, NEW, PROGRESS, SUBMITTED, WORKER, Department, RefreshToken, Task, User,
)
from ..schemas import DepartmentIn, DepartmentOut, PasswordIn, UserIn, UserOut, UserPatch
from ..services import tasks as svc
from .. import clock

router = APIRouter(tags=["admin"])


# ---------------------------------------------------------------- bo'limlar
def _head_of(db: Session, dep_id: int) -> Optional[User]:
    return db.scalar(select(User).where(User.department_id == dep_id, User.role == HEAD,
                                        User.is_active.is_(True)))


def _dep_out(db: Session, d: Department) -> DepartmentOut:
    head = _head_of(db, d.id)
    counts = svc.task_counts(db, [head.id]).get(head.id, {}) if head else {}
    return DepartmentOut(id=d.id, name=d.name, sort_order=d.sort_order, is_active=d.is_active,
                         head_id=head.id if head else None,
                         head_name=head.full_name if head else None,
                         open_tasks=counts.get("open", 0), late_tasks=counts.get("late", 0))


@router.get("/departments", response_model=list[DepartmentOut])
def list_departments(ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db),
                     active: Optional[bool] = None):
    q = select(Department)
    if active is not None:
        q = q.where(Department.is_active.is_(active))
    rows = db.scalars(q.order_by(Department.sort_order, Department.id)).all()
    return [_dep_out(db, d) for d in rows]


@router.post("/departments", response_model=DepartmentOut, status_code=201)
def create_department(body: DepartmentIn, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    ctx.require_manager()
    name = body.name.strip()
    if db.scalar(select(Department).where(func.lower(Department.name) == name.lower(),
                                          Department.is_active.is_(True))):
        raise validation("DUPLICATE", "Bunday nomli bo'lim allaqachon bor.",
                         field_errors={"name": "duplicate"})
    d = Department(name=name, sort_order=body.sort_order)
    db.add(d)
    db.commit()
    db.refresh(d)
    return _dep_out(db, d)


@router.patch("/departments/{dep_id}", response_model=DepartmentOut)
def update_department(dep_id: int, body: DepartmentIn, ctx: Ctx = Depends(get_ctx),
                      db: Session = Depends(get_db)):
    ctx.require_manager()
    d = db.get(Department, dep_id) or _raise_dep()
    d.name = body.name.strip()
    d.sort_order = body.sort_order
    db.commit()
    return _dep_out(db, d)


@router.delete("/departments/{dep_id}")
def delete_department(dep_id: int, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    """Bo'lim o'chirilmaydi, faol emas qilinadi — vazifa tarixi buzilmasin.
    Boshlig'i bo'lsa, avval uni ko'chirish yoki bloklash kerak."""
    ctx.require_manager()
    d = db.get(Department, dep_id) or _raise_dep()
    head = _head_of(db, d.id)
    if head:
        raise validation("DEPARTMENT_HAS_HEAD",
                         f"Avval boshlig'ini ({head.full_name}) boshqa bo'limga o'tkazing yoki bloklang.",
                         field_errors={"head_id": "exists"})
    d.is_active = False
    db.commit()
    return {"ok": True}


def _raise_dep():
    raise not_found("Bo'lim")


# ---------------------------------------------------------------- xodimlar
@router.get("/users", response_model=list[UserOut])
def list_users(ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db),
               role: Optional[str] = None, department_id: Optional[int] = None,
               q: Optional[str] = None, active: Optional[bool] = True,
               assignable: bool = False, limit: int = Query(500, le=1000)):
    """Ijrochi ham chaqira oladi (botda ism ko'rsatish uchun), lekin ro'yxat qisqargan holda:
    faqat ism va rol kerak bo'ladigan joylarda ishlatiladi."""
    sel = select(User)
    if role:
        sel = sel.where(User.role.in_([r.strip() for r in role.split(",") if r.strip()]))
    if department_id:
        sel = sel.where(User.department_id == department_id)
    if active is not None:
        sel = sel.where(User.is_active.is_(active))
    if assignable:
        # vazifa berish mumkin bo'lganlar: boss va assistant bir-biriga ham bera oladi
        sel = sel.where(User.is_active.is_(True))
    if q:
        like = f"%{q.strip().lower()}%"
        sel = sel.where(func.lower(User.full_name).like(like) | func.lower(User.login).like(like)
                        | func.lower(func.coalesce(User.position, "")).like(like))
    rows = db.scalars(sel.order_by(User.role, User.full_name).limit(limit)).all()
    counts = svc.task_counts(db, [u.id for u in rows])
    return [UserOut(**svc.user_out(db, u, ctx.user.lang, counts.get(u.id, {}))) for u in rows]


@router.get("/users/{user_id}", response_model=UserOut)
def get_user(user_id: int, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    u = db.get(User, user_id) or _raise_user()
    counts = svc.task_counts(db, [u.id]).get(u.id, {})
    return UserOut(**svc.user_out(db, u, ctx.user.lang, counts))


def _check_department(db: Session, role: str, department_id: Optional[int], user_id: Optional[int] = None):
    """Bo'lim boshlig'ida bo'lim majburiy va bitta bo'limda bitta boshliq bo'ladi.
    Ijrochi asosiy bo'limga tegishli — unga bo'lim biriktirilmaydi."""
    if role == HEAD:
        if not department_id:
            raise validation("VALIDATION", "Bo'lim boshlig'i uchun bo'lim tanlanishi shart.",
                             field_errors={"department_id": "required"})
        dep = db.get(Department, department_id)
        if not dep or not dep.is_active:
            raise not_found("Bo'lim")
        other = db.scalar(select(User).where(User.department_id == department_id, User.role == HEAD,
                                             User.is_active.is_(True), User.id != (user_id or 0)))
        if other:
            raise validation("DEPARTMENT_TAKEN",
                             f"Bu bo'limning boshlig'i allaqachon bor: {other.full_name}.",
                             field_errors={"department_id": "taken"})
        return department_id
    return None


def _guard_top(ctx: Ctx, *roles: Optional[str]):
    """Boshliq yoki assistant qatoriga tegadigan har qanday amal — faqat boshliqda.
    `roles` ga amalga aloqador rollarni beramiz: odamning hozirgi roli va (bo'lsa)
    unga berilayotgan yangi rol. Shu bilan assistantni assistant ochishi ham,
    ijrochini assistantga ko'tarishi ham, boshliqni bloklashi ham to'siladi."""
    if any(r in MANAGERS for r in roles if r):
        ctx.require_boss()


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(body: UserIn, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    ctx.require_manager()
    _guard_top(ctx, body.role)
    login = body.login.strip().lower()
    if db.scalar(select(User).where(func.lower(User.login) == login)):
        raise validation("LOGIN_TAKEN", "Bu login band.", field_errors={"login": "taken"})
    validate_password_strength(body.password)
    dep_id = _check_department(db, body.role, body.department_id)
    u = User(full_name=body.full_name.strip(), login=login, phone=(body.phone or "").strip() or None,
             password_hash=hash_password(body.password), role=body.role,
             position=(body.position or "").strip() or None, department_id=dep_id, lang=body.lang)
    db.add(u)
    db.commit()
    db.refresh(u)
    return UserOut(**svc.user_out(db, u, ctx.user.lang))


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(user_id: int, body: UserPatch, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    u = db.get(User, user_id) or _raise_user()
    # Har kim o'z tilini o'zgartira oladi; qolgan hamma narsa faqat boshqaruvchida.
    only_lang = {k for k, v in body.model_dump(exclude_unset=True).items() if v is not None} <= {"lang"}
    if not (only_lang and u.id == ctx.user.id):
        ctx.require_manager()
        # o'z profilini har kim `/auth/me` orqali o'zgartiradi; bu yer boshqa odam uchun
        if u.id != ctx.user.id:
            _guard_top(ctx, u.role, body.model_dump(exclude_unset=True).get("role"))

    data = body.model_dump(exclude_unset=True)
    if "login" in data and data["login"]:
        login = data["login"].strip().lower()
        if db.scalar(select(User).where(func.lower(User.login) == login, User.id != u.id)):
            raise validation("LOGIN_TAKEN", "Bu login band.", field_errors={"login": "taken"})
        u.login = login
    new_role = data.get("role") or u.role
    if "role" in data or "department_id" in data:
        dep = data.get("department_id", u.department_id)
        u.department_id = _check_department(db, new_role, dep, user_id=u.id)
        u.role = new_role
    for f in ("full_name", "position", "phone", "lang"):
        if f in data and data[f] is not None:
            setattr(u, f, (data[f].strip() or None) if isinstance(data[f], str) else data[f])
    if u.full_name is None:
        raise validation("VALIDATION", "Ism bo'sh bo'lmasligi kerak.", field_errors={"full_name": "required"})
    if "is_active" in data and data["is_active"] is not None:
        _set_active(db, ctx, u, bool(data["is_active"]))
    db.commit()
    db.refresh(u)
    counts = svc.task_counts(db, [u.id]).get(u.id, {})
    return UserOut(**svc.user_out(db, u, ctx.user.lang, counts))


def _set_active(db: Session, ctx: Ctx, u: User, active: bool):
    if not active:
        if u.id == ctx.user.id:
            raise validation("SELF_BLOCK", "O'zingizni bloklay olmaysiz.")
        if u.role == "boss" and db.execute(select(func.count()).select_from(User).where(
                User.role == "boss", User.is_active.is_(True))).scalar() <= 1:
            raise validation("LAST_BOSS", "Yagona boshliqni bloklab bo'lmaydi.")
        open_n = db.execute(select(func.count()).select_from(Task).where(
            Task.assignee_id == u.id, Task.status.in_((NEW, PROGRESS, SUBMITTED)))).scalar() or 0
        if open_n:
            raise validation("HAS_OPEN_TASKS",
                             f"Bu odamda {open_n} ta ochiq vazifa bor. Avval ularni boshqasiga bering yoki yoping.",
                             field_errors={"is_active": "has_open_tasks"}, open_tasks=open_n)
        for rt in db.scalars(select(RefreshToken).where(RefreshToken.user_id == u.id,
                                                        RefreshToken.revoked.is_(False))):
            rt.revoked = True
    u.is_active = active


@router.post("/users/{user_id}/block", response_model=UserOut)
def block_user(user_id: int, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    ctx.require_manager()
    u = db.get(User, user_id) or _raise_user()
    _guard_top(ctx, u.role)
    _set_active(db, ctx, u, False)
    db.commit()
    return UserOut(**svc.user_out(db, u, ctx.user.lang))


@router.post("/users/{user_id}/unblock", response_model=UserOut)
def unblock_user(user_id: int, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    ctx.require_manager()
    u = db.get(User, user_id) or _raise_user()
    _guard_top(ctx, u.role)
    # bloklangan boshliq qaytsa, bo'limi band bo'lib qolgan bo'lishi mumkin
    if u.role == HEAD:
        _check_department(db, HEAD, u.department_id, user_id=u.id)
    u.is_active = True
    db.commit()
    return UserOut(**svc.user_out(db, u, ctx.user.lang))


@router.post("/users/{user_id}/password")
def set_password(user_id: int, body: PasswordIn, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    ctx.require_manager()
    u = db.get(User, user_id) or _raise_user()
    if u.id != ctx.user.id:
        _guard_top(ctx, u.role)
    validate_password_strength(body.password)
    u.password_hash = hash_password(body.password)
    for rt in db.scalars(select(RefreshToken).where(RefreshToken.user_id == u.id,
                                                    RefreshToken.revoked.is_(False))):
        rt.revoked = True
    db.commit()
    return {"ok": True}


def _raise_user():
    raise not_found("Foydalanuvchi")
