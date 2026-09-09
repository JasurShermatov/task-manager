from datetime import datetime

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import Ctx, get_ctx, hash_password, make_access_token, make_refresh_token, validate_password_strength, verify_password
from ..config import settings
from ..db import get_db
from ..errors import ApiError, unauthorized
from ..models import RefreshToken, User
from ..redis_client import rds
from ..schemas import LoginIn, MeIn, RefreshIn, TokenOut, UserOut
from ..services import tasks as svc

router = APIRouter(prefix="/auth", tags=["auth"])


def _attempt_key(login: str, ip: str) -> str:
    return f"login_attempts:{login.lower()}:{ip}"


def _token_out(db: Session, user: User) -> TokenOut:
    return TokenOut(access_token=make_access_token(user), refresh_token=make_refresh_token(db, user),
                    expires_in=settings.ACCESS_TTL_MIN * 60,
                    user=UserOut(**svc.user_out(db, user, user.lang)))


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    ip = request.client.host if request.client else "?"
    key = _attempt_key(body.login, ip)
    attempts = int(rds.get(key) or 0)
    if attempts >= 5:
        raise ApiError(429, "TOO_MANY_ATTEMPTS", "Ko'p urinish. 15 daqiqadan keyin qayta urinib ko'ring.")
    user = db.scalar(select(User).where(User.login == body.login))
    if not user or not user.is_active or not verify_password(body.password, user.password_hash):
        rds.set(key, attempts + 1, ex=900)
        raise unauthorized("Login yoki parol noto'g'ri.")
    rds.delete(key)
    user.last_login_at = datetime.utcnow()
    db.commit()
    return _token_out(db, user)


@router.post("/refresh", response_model=TokenOut)
def refresh(body: RefreshIn, db: Session = Depends(get_db)):
    rt = db.scalar(select(RefreshToken).where(RefreshToken.token == body.refresh_token))
    if not rt or rt.revoked or rt.expires_at < datetime.utcnow():
        raise unauthorized()
    user = db.get(User, rt.user_id)
    if not user or not user.is_active:
        raise unauthorized()
    rt.revoked = True
    db.commit()
    return _token_out(db, user)


@router.post("/logout")
def logout(body: RefreshIn, db: Session = Depends(get_db)):
    rt = db.scalar(select(RefreshToken).where(RefreshToken.token == body.refresh_token))
    if rt:
        rt.revoked = True
        db.commit()
    return {"ok": True}


@router.get("/me", response_model=UserOut)
def me(ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    counts = svc.task_counts(db, [ctx.user.id]).get(ctx.user.id, {})
    return UserOut(**svc.user_out(db, ctx.user, ctx.user.lang, counts))


@router.patch("/me", response_model=UserOut)
def update_me(body: MeIn, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    u = ctx.user
    if body.full_name:
        u.full_name = body.full_name.strip()
    if body.phone is not None:
        u.phone = body.phone.strip() or None
    if body.lang:
        u.lang = body.lang
    if body.password:
        validate_password_strength(body.password)
        u.password_hash = hash_password(body.password)
        # parol almashsa eski sessiyalar yopiladi
        for rt in db.scalars(select(RefreshToken).where(RefreshToken.user_id == u.id, RefreshToken.revoked.is_(False))):
            rt.revoked = True
    db.commit()
    db.refresh(u)
    return UserOut(**svc.user_out(db, u, u.lang))
