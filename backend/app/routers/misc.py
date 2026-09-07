from __future__ import annotations

import random
from datetime import datetime, timedelta, date
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, Header
from fastapi.responses import FileResponse
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from ..auth import Ctx, get_ctx, get_service
from ..config import settings
from ..db import get_db
from ..errors import validation, not_found, unauthorized, ApiError
from ..models import TelegramLinkCode, User, Notification, TaskAttachment, Task
from ..schemas import LinkCodeOut, NotificationOut, UserOut
from ..services import files as fsvc
from ..services import tasks as svc

router = APIRouter(tags=["misc"])


# ---------- telegram (user side) ----------
@router.post("/telegram/link-code", response_model=LinkCodeOut)
def link_code(ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    # invalidate previous codes
    for c in db.scalars(select(TelegramLinkCode).where(TelegramLinkCode.user_id == ctx.user.id, TelegramLinkCode.used == False)):  # noqa
        c.used = True
    for _ in range(20):
        code = f"{random.randint(0, 999999):06d}"
        if not db.get(TelegramLinkCode, code):
            break
    row = TelegramLinkCode(code=code, user_id=ctx.user.id, expires_at=datetime.utcnow() + timedelta(minutes=10))
    db.add(row)
    db.commit()
    return LinkCodeOut(code=code, expires_at=row.expires_at, bot_username=None)


@router.delete("/telegram/unlink")
def unlink(ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    ctx.user.telegram_user_id = None
    ctx.user.telegram_linked_at = None
    db.commit()
    return {"ok": True}


# ---------- telegram (bot / service side) ----------
@router.post("/telegram/consume-code", response_model=UserOut, dependencies=[Depends(get_service)])
def consume_code(body: dict, db: Session = Depends(get_db)):
    code = str(body.get("code", "")).strip()
    tg_id = int(body.get("telegram_user_id", 0))
    row = db.get(TelegramLinkCode, code)
    if not row or row.used or row.expires_at < datetime.utcnow():
        raise validation("CODE_INVALID", "Kod noto'g'ri yoki muddati o'tgan.")
    u = db.get(User, row.user_id)
    if not u or not u.is_active:
        raise validation("CODE_INVALID", "Foydalanuvchi faol emas.")
    other = db.scalar(select(User).where(User.telegram_user_id == tg_id, User.id != u.id))
    if other:
        raise validation("TELEGRAM_ALREADY_LINKED", "Bu Telegram hisob boshqa foydalanuvchiga bog'langan. Avval uzing.")
    row.used = True
    u.telegram_user_id = tg_id
    u.telegram_linked_at = datetime.utcnow()
    db.commit()
    db.refresh(u)
    return u


@router.get("/telegram/user-by-tg/{tg_id}", response_model=UserOut, dependencies=[Depends(get_service)])
def user_by_tg(tg_id: int, db: Session = Depends(get_db)):
    u = db.scalar(select(User).where(User.telegram_user_id == tg_id, User.is_active == True))  # noqa
    if not u:
        raise not_found("Foydalanuvchi")
    return u


@router.get("/telegram/outbox", dependencies=[Depends(get_service)])
def outbox(limit: int = 50, db: Session = Depends(get_db)):
    """Pending telegram notifications for the bot worker."""
    rows = db.scalars(select(Notification).where(Notification.channel == "telegram", Notification.status == "pending")
                      .order_by(Notification.id).limit(limit)).all()
    out = []
    for n in rows:
        u = db.get(User, n.user_id)
        if not u or not u.telegram_user_id or not u.is_active:
            n.status = "failed"
            continue
        out.append({"id": n.id, "telegram_user_id": u.telegram_user_id, "lang": u.lang, "event": n.event,
                    "payload": n.payload_json, "task_id": n.task_id, "created_at": n.created_at.isoformat()})
    db.commit()
    return out


@router.post("/telegram/outbox/ack", dependencies=[Depends(get_service)])
def outbox_ack(body: dict, db: Session = Depends(get_db)):
    sent = body.get("sent", [])
    failed = body.get("failed", [])
    for n in db.scalars(select(Notification).where(Notification.id.in_(sent or [0]))):
        n.status, n.sent_at = "sent", datetime.utcnow()
    for n in db.scalars(select(Notification).where(Notification.id.in_(failed or [0]))):
        n.status = "failed"
        # fallback: in-app copy so the user still sees it
        db.add(Notification(user_id=n.user_id, task_id=n.task_id, event=n.event, payload_json=n.payload_json,
                            channel="inapp", status="sent", sent_at=datetime.utcnow()))
    db.commit()
    return {"ok": True}


# ---------- in-app notifications ----------
@router.get("/notifications", response_model=List[NotificationOut])
def notifications(ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db), unread: bool = False, limit: int = Query(50, le=200)):
    q = select(Notification).where(Notification.user_id == ctx.user.id, Notification.channel == "inapp")
    if unread:
        q = q.where(Notification.is_read == False)  # noqa
    return db.scalars(q.order_by(Notification.id.desc()).limit(limit)).all()


@router.get("/notifications/unread-count")
def unread_count(ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    n = db.execute(select(func.count()).select_from(Notification).where(
        Notification.user_id == ctx.user.id, Notification.channel == "inapp", Notification.is_read == False)).scalar()  # noqa
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


# ---------- files (signed) ----------
@router.get("/files/{att_id}")
def get_file(att_id: int, exp: int, sig: str, db: Session = Depends(get_db)):
    if not fsvc.verify_sig(att_id, exp, sig):
        raise unauthorized("Havola muddati tugagan.")
    att = db.get(TaskAttachment, att_id)
    if not att or not att.is_active:
        raise not_found("Fayl")
    return FileResponse(fsvc.abs_path(att.storage_key), media_type=att.mime_type, filename=att.filename)


@router.get("/files/{att_id}/sign", dependencies=[Depends(get_service)])
def sign_file(att_id: int, db: Session = Depends(get_db)):
    att = db.get(TaskAttachment, att_id) or (_ for _ in ()).throw(not_found("Fayl"))
    return {"url": fsvc.signed_url(att.id, 900), "path": fsvc.abs_path(att.storage_key)}


@router.get("/health")
def health(db: Session = Depends(get_db)):
    db.execute(select(1))
    return {"ok": True, "time": datetime.utcnow().isoformat()}


@router.get("/meta")
def meta(ctx: Ctx = Depends(get_ctx)):
    from ..models import BLOCK_REASONS, TASK_STATUSES, PRIORITIES, EVIDENCE_KINDS
    return {"statuses": TASK_STATUSES, "priorities": PRIORITIES, "block_reasons": BLOCK_REASONS,
            "evidence_kinds": EVIDENCE_KINDS, "units": ["m3", "m2", "m", "t", "dona", "pog.m", "kg", "l"],
            "voice_enabled": bool(settings.OPENAI_API_KEY), "password_min": settings.MIN_PASSWORD_LEN}
