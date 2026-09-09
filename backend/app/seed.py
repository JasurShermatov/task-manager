"""Idempotent seed: bitta boss va bot sozlamasi. Boshqa hech narsa yaratilmaydi —
bo'limlarni va xodimlarni boss o'zi administratsiyadan kiritadi."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import hash_password
from .config import settings
from .models import BOSS, AppSetting, User


def seed(db: Session):
    if not db.scalar(select(User).limit(1)):
        db.add(User(full_name="Boshliq", login=settings.ADMIN_LOGIN,
                    password_hash=hash_password(settings.ADMIN_PASSWORD),
                    role=BOSS, lang="uz"))
    if not db.get(AppSetting, "bot_username"):
        db.add(AppSetting(key="bot_username", value=(settings.BOT_USERNAME or "").lstrip("@")))
    # Eslatma soatlari sozlamadan o'qiladi — kod tegmasdan o'zgartirish uchun.
    if not db.get(AppSetting, "reminder_hours"):
        db.add(AppSetting(key="reminder_hours", value="9,13,17"))
    db.commit()
