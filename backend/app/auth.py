"""Kirish, tokenlar va so'rov konteksti.

Vaqt: JWT va refresh token **UTC**'da (standart shunday). Domen vaqti mahalliy — `clock.py`.
"""
import secrets
from datetime import datetime, timedelta
from typing import Optional

import bcrypt
import jwt
from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .errors import permission_denied, scope_forbidden, unauthorized
from .models import MANAGERS, RefreshToken, Task, User


# ---------- parollar ----------
# Ichki tizim: parol qisqa bo'lishi mumkin (MIN_PASSWORD_LEN). Asosiy himoya — urinishlar
# limiti (5 xatodan keyin 15 daqiqa qulf) va JWT ning qisqa muddati.

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


# ---------- tokenlar ----------
def make_access_token(user: User) -> str:
    exp = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TTL_MIN)
    return jwt.encode({"sub": str(user.id), "exp": exp, "typ": "access"}, settings.JWT_SECRET, algorithm="HS256")


def make_refresh_token(db: Session, user: User) -> str:
    tok = secrets.token_urlsafe(48)
    db.add(RefreshToken(user_id=user.id, token=tok,
                        expires_at=datetime.utcnow() + timedelta(days=settings.REFRESH_TTL_DAYS)))
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


# ---------- so'rov konteksti ----------
class Ctx:
    def __init__(self, user: User, source: str, request_id: str):
        self.user = user
        self.source = source
        self.request_id = request_id

    @property
    def role(self) -> str:
        return self.user.role

    @property
    def is_manager(self) -> bool:
        return self.user.role in MANAGERS

    def require_manager(self):
        """Boss va assistant huquqda teng — ikkalasi ham o'tadi."""
        if not self.is_manager:
            raise permission_denied()


def get_ctx(request: Request,
            authorization: Optional[str] = Header(None),
            x_service_token: Optional[str] = Header(None),
            x_acting_user_id: Optional[int] = Header(None),
            x_source: Optional[str] = Header(None),
            x_request_id: Optional[str] = Header(None),
            db: Session = Depends(get_db)) -> Ctx:
    user = None
    source = x_source if x_source in ("web", "bot") else "web"
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


# ---------- vazifaga kirish ----------
def can_see_task(ctx: Ctx, task: Task) -> bool:
    """Boshqaruvchi hamma vazifani ko'radi. Ijrochi — faqat o'ziga berilganini.
    Bo'lim boshlig'i o'z bo'limidagi boshqa odamning vazifasini ko'rmaydi: bo'lim ichidagi
    ishchilar platformada yo'q, asosiy bo'lim esa to'g'ridan-to'g'ri boshliqqa qaraydi."""
    return ctx.is_manager or task.assignee_id == ctx.user.id


def check_task_access(ctx: Ctx, task: Task):
    if not can_see_task(ctx, task):
        raise scope_forbidden()
