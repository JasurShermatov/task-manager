from __future__ import annotations

import random
import re
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import clock
from ..auth import Ctx, get_ctx, get_service
from ..config import settings
from ..db import get_db
from ..errors import not_found, unauthorized, validation
from ..models import ROLES, TASK_STATUSES, AppSetting, Notification, TaskFile, TelegramLinkCode, User
from ..roles import ROLE_NAMES
from ..schemas import ConsumeCodeIn, LinkCodeOut, OutboxAckIn, UserOut
from ..services import files as fsvc
from ..services import tasks as svc

router = APIRouter(tags=["misc"])


# ---------- telegram (foydalanuvchi tomoni) ----------
@router.post("/telegram/link-code", response_model=LinkCodeOut)
def link_code(ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    for c in db.scalars(select(TelegramLinkCode).where(TelegramLinkCode.user_id == ctx.user.id,
                                                       TelegramLinkCode.used.is_(False))):
        c.used = True
    code = f"{random.randint(0, 999999):06d}"
    for _ in range(20):
        if not db.get(TelegramLinkCode, code):
            break
        code = f"{random.randint(0, 999999):06d}"
    row = TelegramLinkCode(code=code, user_id=ctx.user.id,
                           expires_at=datetime.utcnow() + timedelta(minutes=10))
    db.add(row)
    db.commit()
    bot = get_setting(db, "bot_username")
    return LinkCodeOut(code=code, expires_at=row.expires_at,
                       deep_link=f"https://t.me/{bot}?start={code}" if bot else None)


@router.delete("/telegram/unlink")
def unlink(ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    ctx.user.telegram_user_id = None
    ctx.user.telegram_linked_at = None
    db.commit()
    return {"ok": True}


# ---------- telegram (bot / xizmat tomoni) ----------
@router.post("/telegram/consume-code", response_model=UserOut, dependencies=[Depends(get_service)])
def consume_code(body: ConsumeCodeIn, db: Session = Depends(get_db)):
    row = db.get(TelegramLinkCode, body.code.strip())
    if not row or row.used or row.expires_at < datetime.utcnow():
        raise validation("CODE_INVALID", "Kod noto'g'ri yoki muddati o'tgan.")
    u = db.get(User, row.user_id)
    if not u or not u.is_active:
        raise validation("CODE_INVALID", "Foydalanuvchi faol emas.")
    other = db.scalar(select(User).where(User.telegram_user_id == body.telegram_user_id, User.id != u.id))
    if other:
        raise validation("TELEGRAM_ALREADY_LINKED",
                         "Bu Telegram hisob boshqa foydalanuvchiga bog'langan. Avval uzing.")
    row.used = True
    u.telegram_user_id = body.telegram_user_id
    u.telegram_linked_at = datetime.utcnow()
    db.commit()
    return UserOut(**svc.user_out(db, u, u.lang))


@router.get("/telegram/user-by-tg/{tg_id}", response_model=UserOut, dependencies=[Depends(get_service)])
def user_by_tg(tg_id: int, db: Session = Depends(get_db)):
    u = db.scalar(select(User).where(User.telegram_user_id == tg_id, User.is_active.is_(True)))
    if not u:
        raise not_found("Foydalanuvchi")
    counts = svc.task_counts(db, [u.id]).get(u.id, {})
    return UserOut(**svc.user_out(db, u, u.lang, counts))


@router.post("/telegram/register-username", dependencies=[Depends(get_service)])
def register_bot_username(body: dict, db: Session = Depends(get_db)):
    """Bot ishga tushganda o'z username'ini xabar qiladi — qo'lda kiritish shart emas."""
    val = str(body.get("username") or "").strip().lstrip("@")
    if not val:
        raise validation("VALIDATION", "username bo'sh.")
    _set_setting(db, "bot_username", val)
    db.commit()
    return {"bot_username": val}


# Bitta tokenga bitta ishlaydigan bot. Ikkinchi nusxa (masalan, mahalliy kompyuterda)
# ishga tushsa, Telegram yangilanishlarni ikkiga bo'lib yuboradi: odam kod kiritadi, uni
# ikkinchi nusxa ushlab, boshqa bazadan qidiradi va "kod noto'g'ri" deydi — foydalanuvchi
# uchun bu "bot uzilib qoldi" bo'lib ko'rinadi. Shuning uchun ijozat (lease) shu yerda
# beriladi: birinchi kelgan ishlaydi, ikkinchisi kutadi va birinchisi to'xtagach o'zi oladi.
BOT_LEASE_TTL = 90    # soniya; bot har 30 soniyada yangilab turadi


@router.post("/telegram/bot-lease", dependencies=[Depends(get_service)])
def bot_lease(body: dict, db: Session = Depends(get_db)):
    me = str(body.get("instance_id") or "").strip()[:80]
    if not me:
        raise validation("VALIDATION", "instance_id bo'sh.")
    now = datetime.utcnow()
    holder, since = "", None
    raw = get_setting(db, "bot_lease")
    if "|" in raw:
        holder, ts = raw.split("|", 1)
        try:
            since = datetime.fromisoformat(ts)
        except ValueError:
            since = None
    age = (now - since).total_seconds() if since else None
    granted = holder in ("", me) or age is None or age > BOT_LEASE_TTL
    if granted:
        _set_setting(db, "bot_lease", f"{me}|{now.isoformat(timespec='seconds')}")
        db.commit()
    return {"granted": granted, "holder": holder if not granted else me,
            "age": round(age) if age is not None else None, "ttl": BOT_LEASE_TTL}


@router.get("/telegram/outbox", dependencies=[Depends(get_service)])
def outbox(limit: int = Query(50, le=200), db: Session = Depends(get_db)):
    rows = db.scalars(select(Notification)
                      .where(Notification.channel == "telegram", Notification.status == "pending")
                      .order_by(Notification.id).limit(limit)).all()
    out = []
    for n in rows:
        u = db.get(User, n.user_id)
        if not u or not u.telegram_user_id or not u.is_active:
            n.status = "failed"
            continue
        out.append({"id": n.id, "telegram_user_id": u.telegram_user_id, "lang": u.lang,
                    "event": n.event, "payload": n.payload_json, "task_id": n.task_id,
                    "created_at": n.created_at.isoformat()})
    db.commit()
    return out


@router.post("/telegram/outbox/ack", dependencies=[Depends(get_service)])
def outbox_ack(body: OutboxAckIn, db: Session = Depends(get_db)):
    for n in db.scalars(select(Notification).where(Notification.id.in_(body.sent or [0]))):
        n.status, n.sent_at = "sent", clock.now()
    for n in db.scalars(select(Notification).where(Notification.id.in_(body.failed or [0]))):
        n.status = "failed"
        # Telegram yetib bormasa, web'da ko'rinsin
        db.add(Notification(user_id=n.user_id, task_id=n.task_id, event=n.event,
                            payload_json=n.payload_json, channel="inapp", status="sent",
                            sent_at=clock.now()))
    db.commit()
    return {"ok": True}


# ---------- web ichidagi bildirishnomalar ----------
@router.get("/notifications")
def notifications(ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db),
                  unread: bool = False, limit: int = Query(50, le=200)):
    q = select(Notification).where(Notification.user_id == ctx.user.id, Notification.channel == "inapp")
    if unread:
        q = q.where(Notification.is_read.is_(False))
    rows = db.scalars(q.order_by(Notification.id.desc()).limit(limit)).all()
    return [{"id": n.id, "event": n.event, "payload": n.payload_json, "task_id": n.task_id,
             "is_read": n.is_read, "created_at": n.created_at} for n in rows]


@router.get("/notifications/unread-count")
def unread_count(ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    n = db.execute(select(func.count()).select_from(Notification).where(
        Notification.user_id == ctx.user.id, Notification.channel == "inapp",
        Notification.is_read.is_(False))).scalar()
    return {"count": n or 0}


@router.post("/notifications/read")
def mark_read(body: dict, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    ids = body.get("ids")
    q = select(Notification).where(Notification.user_id == ctx.user.id, Notification.channel == "inapp")
    if ids:
        q = q.where(Notification.id.in_(ids))
    for n in db.scalars(q):
        n.is_read = True
    db.commit()
    return {"ok": True}


# ---------- fayllar (imzolangan havola) ----------
@router.get("/files/{file_id}")
def get_file(file_id: int, exp: int, sig: str, db: Session = Depends(get_db)):
    if not fsvc.verify_sig(file_id, exp, sig):
        raise unauthorized("Havola muddati tugagan.")
    row = db.get(TaskFile, file_id)
    if not row or not row.is_active:
        raise not_found("Fayl")
    return FileResponse(fsvc.abs_path(row.storage_key), media_type=row.mime_type, filename=row.filename)


@router.get("/files/{file_id}/sign", dependencies=[Depends(get_service)])
def sign_file(file_id: int, db: Session = Depends(get_db)):
    row = db.get(TaskFile, file_id)
    if not row:
        raise not_found("Fayl")
    return {"url": fsvc.signed_url(row.id, 900), "path": fsvc.abs_path(row.storage_key)}


# ---------- sozlamalar ----------
PUBLIC_SETTINGS = {"bot_username"}
MANAGER_SETTINGS = {"bot_username", "reminder_hours"}


def get_setting(db: Session, key: str, default: str = "") -> str:
    row = db.get(AppSetting, key)
    return (row.value if row and row.value else default) or default


def _set_setting(db: Session, key: str, value: str, by: Optional[int] = None):
    row = db.get(AppSetting, key)
    if row:
        row.value, row.updated_by = value, by
    else:
        db.add(AppSetting(key=key, value=value, updated_by=by))


@router.get("/settings")
def settings_read(ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    rows = {r.key: r.value for r in db.scalars(select(AppSetting))}
    bot = (rows.get("bot_username") or "").lstrip("@")
    out = {"bot_username": bot, "bot_url": f"https://t.me/{bot}" if bot else ""}
    if ctx.is_manager:
        out["reminder_hours"] = rows.get("reminder_hours") or "9,13,17"
    return out


@router.patch("/settings")
def settings_write(body: dict, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    ctx.require_manager()
    for key, value in body.items():
        if key not in MANAGER_SETTINGS:
            raise validation("VALIDATION", f"Noma'lum sozlama: {key}")
        val = str(value or "").strip()
        if key == "bot_username":
            val = val.lstrip("@")
            if val and not re.fullmatch(r"[A-Za-z0-9_]{4,32}", val):
                raise validation("VALIDATION", "Bot username 4-32 belgi: harf, raqam va _ dan iborat.",
                                 field_errors={"bot_username": "invalid"})
        if key == "reminder_hours":
            try:
                hours = sorted({int(x) for x in val.split(",") if x.strip() != ""})
            except ValueError:
                hours = []
            if not hours or any(h < 0 or h > 23 for h in hours) or len(hours) > 6:
                raise validation("VALIDATION", "Eslatma soatlari: 0-23 oralig'ida, vergul bilan (masalan 9,13,17).",
                                 field_errors={"reminder_hours": "invalid"})
            val = ",".join(str(h) for h in hours)
        _set_setting(db, key, val, ctx.user.id)
    db.commit()
    return settings_read(ctx, db)


@router.get("/health")
def health(db: Session = Depends(get_db)):
    db.execute(select(1))
    return {"ok": True, "time": clock.now().isoformat()}


@router.get("/meta")
def meta(ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    lang = ctx.user.lang
    hours = [int(x) for x in (get_setting(db, "reminder_hours", "9,13,17")).split(",") if x.strip()]
    return {
        "roles": [{"code": r, "name": ROLE_NAMES.get(lang, ROLE_NAMES["uz"])[r]} for r in ROLES],
        "statuses": list(TASK_STATUSES),
        "bot_username": get_setting(db, "bot_username"),
        "reminder_hours": hours,
        "voice_enabled": bool(settings.OPENAI_API_KEY),
        "password_min": settings.MIN_PASSWORD_LEN,
        "is_manager": ctx.is_manager,
    }
