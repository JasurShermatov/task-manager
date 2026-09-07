from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import (verify_password, make_access_token, make_refresh_token, get_ctx, Ctx)
from ..config import settings
from ..db import get_db
from ..errors import ApiError, unauthorized
from ..models import User, RefreshToken
from ..schemas import LoginIn, TokenOut, RefreshIn, MeOut, UserOut
from ..redis_client import rds

router = APIRouter(prefix="/auth", tags=["auth"])


def _attempt_key(login: str, ip: str) -> str:
    return f"login_attempts:{login.lower()}:{ip}"


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
    return TokenOut(access_token=make_access_token(user), refresh_token=make_refresh_token(db, user),
                    expires_in=settings.ACCESS_TTL_MIN * 60)


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
    return TokenOut(access_token=make_access_token(user), refresh_token=make_refresh_token(db, user),
                    expires_in=settings.ACCESS_TTL_MIN * 60)


@router.post("/logout")
def logout(body: RefreshIn, db: Session = Depends(get_db)):
    rt = db.scalar(select(RefreshToken).where(RefreshToken.token == body.refresh_token))
    if rt:
        rt.revoked = True
        db.commit()
    return {"ok": True}


@router.get("/me", response_model=MeOut)
def me(ctx: Ctx = Depends(get_ctx)):
    u = ctx.user
    return MeOut(user=UserOut.model_validate(u), permissions=sorted(ctx.perms),
                 scope={"type": u.scope_type, "id": u.scope_id})
