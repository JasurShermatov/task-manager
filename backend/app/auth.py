import secrets
from datetime import datetime, timedelta
from typing import Optional

import bcrypt
import jwt
from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .errors import unauthorized, permission_denied, scope_forbidden
from .models import User, Task, Location, RefreshToken


# ---------- passwords ----------
# Ichki tizim: parol qisqa bo'lishi mumkin (MIN_PASSWORD_LEN). Asosiy himoya - urinishlar limiti
# (5 xatodan keyin 15 daqiqa qulf) va JWT ning qisqa muddati.


def hash_password(p: str) -> str:
    return bcrypt.hashpw(p.encode(), bcrypt.gensalt()).decode()


def verify_password(p: str, h: str) -> bool:
    try:
        return bcrypt.checkpw(p.encode(), h.encode())
    except Exception:
        return False


def validate_password_strength(p: str):
    from .errors import validation
    n = settings.MIN_PASSWORD_LEN
    if len(p or "") < n:
        raise validation("WEAK_PASSWORD", f"Parol kamida {n} belgidan iborat bo'lishi kerak.",
                         field_errors={"password": f"min {n}"}, min_length=n)


# ---------- tokens ----------
def make_access_token(user: User) -> str:
    exp = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TTL_MIN)
    return jwt.encode({"sub": str(user.id), "exp": exp, "typ": "access"}, settings.JWT_SECRET, algorithm="HS256")


def make_refresh_token(db: Session, user: User) -> str:
    tok = secrets.token_urlsafe(48)
    db.add(RefreshToken(user_id=user.id, token=tok, expires_at=datetime.utcnow() + timedelta(days=settings.REFRESH_TTL_DAYS)))
    db.commit()
    return tok


def decode_access(token: str) -> Optional[int]:
    try:
        data = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
        if data.get("typ") != "access":
            return None
        return int(data["sub"])
    except Exception:
        return None


# ---------- request context ----------
class Ctx:
    def __init__(self, user: User, source: str, request_id: str):
        self.user = user
        self.source = source
        self.request_id = request_id

    @property
    def perms(self) -> set:
        return set(self.user.role.permissions_json or [])

    def has(self, perm: str) -> bool:
        return perm in self.perms

    def require(self, perm: str):
        if not self.has(perm):
            raise permission_denied()


def get_ctx(request: Request,
            authorization: Optional[str] = Header(None),
            x_service_token: Optional[str] = Header(None),
            x_acting_user_id: Optional[int] = Header(None),
            x_source: Optional[str] = Header(None),
            x_request_id: Optional[str] = Header(None),
            db: Session = Depends(get_db)) -> Ctx:
    user = None
    source = x_source if x_source in ("web", "mobile", "bot") else "web"
    if x_service_token:
        if x_service_token != settings.SERVICE_TOKEN or not x_acting_user_id:
            raise unauthorized("Xizmat tokeni noto'g'ri.")
        user = db.get(User, x_acting_user_id)
        source = x_source or "bot"
    elif authorization and authorization.lower().startswith("bearer "):
        uid = decode_access(authorization.split(" ", 1)[1].strip())
        if uid:
            user = db.get(User, uid)
    if not user or not user.is_active:
        raise unauthorized()
    return Ctx(user, source, x_request_id or secrets.token_hex(8))


def get_service(x_service_token: Optional[str] = Header(None)):
    if x_service_token != settings.SERVICE_TOKEN:
        raise unauthorized("Xizmat tokeni noto'g'ri.")
    return True


# ---------- scope ----------
def location_root(db: Session, location_id: Optional[int]) -> Optional[int]:
    """Returns the top-level (block) id of a location."""
    cur = db.get(Location, location_id) if location_id else None
    while cur and cur.parent_id:
        cur = db.get(Location, cur.parent_id)
    return cur.id if cur else None


def location_in_scope(db: Session, location_id: Optional[int], scope_loc_id: int) -> bool:
    cur = db.get(Location, location_id) if location_id else None
    while cur:
        if cur.id == scope_loc_id:
            return True
        cur = db.get(Location, cur.parent_id) if cur.parent_id else None
    return False


def scope_project_id(db: Session, u: User) -> Optional[int]:
    """Foydalanuvchi doirasi qaysi loyihaga tegishli (uchastka bo'lsa - blokning loyihasi)."""
    if u.scope_type == "project":
        return u.scope_id
    if u.scope_type == "location":
        loc = db.get(Location, u.scope_id)
        return loc.project_id if loc else None
    return None


def user_in_project(u: User, project_id: int, db: Session) -> bool:
    if u.scope_type == "system":
        return True
    if u.scope_type == "project":
        return u.scope_id == project_id
    if u.scope_type == "location":
        loc = db.get(Location, u.scope_id)
        return bool(loc and loc.project_id == project_id)
    return False


def check_task_scope(ctx: Ctx, task: Task, db: Session):
    u = ctx.user
    role = u.role.code
    if role == "bajaruvchi":
        if task.assignee_id != u.id and task.reviewer_id != u.id and task.created_by != u.id:
            raise scope_forbidden()
        return
    if u.scope_type == "system":
        return
    if u.scope_type == "project":
        if task.project_id != u.scope_id:
            raise scope_forbidden()
        return
    if u.scope_type == "location":
        if location_in_scope(db, task.location_id, u.scope_id):
            return
        # joy ko'rsatilmagan (butun obyekt bo'yicha) vazifa ham uchastka boshlig'iga tegishli
        if task.location_id is None and scope_project_id(db, u) == task.project_id:
            return
        if task.assignee_id == u.id or task.reviewer_id == u.id:
            return
        raise scope_forbidden()
    raise scope_forbidden()


def check_project_scope(ctx: Ctx, project_id: int, location_id: Optional[int], db: Session):
    u = ctx.user
    if u.scope_type == "system":
        return
    if u.scope_type == "project":
        if u.scope_id != project_id:
            raise scope_forbidden()
        return
    if u.scope_type == "location":
        if location_id and location_in_scope(db, location_id, u.scope_id):
            return
        if location_id is None and scope_project_id(db, u) == project_id:
            return
        raise scope_forbidden()
    raise scope_forbidden()
