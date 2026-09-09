"""SAFF Vazifalar 2.0 — baza modeli.

Tuzilma: boss va assistant (teng huquq) vazifa beradi; bo'lim boshliqlari va asosiy bo'lim
ijrochilari vazifani dalil bilan topshiradi. Obyekt/loyiha/ish turi tuzilmasi yo'q —
vazifa faqat odamga beriladi.

Vaqt: domen ustunlari mahalliy vaqtda (`clock.now`), refresh token esa UTC'da (`auth.py`).
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, JSON,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .clock import now
from .db import Base

# SQLite faqat oddiy INTEGER birlamchi kalitni avtomatik oshiradi; Postgres BIGINT'da qoladi.
PK = BigInteger().with_variant(Integer, "sqlite")

# --- rollar ---
BOSS = "boss"
ASSISTANT = "assistant"
HEAD = "bolim_boshligi"      # tashqi bo'lim boshlig'i (ostidagi ishchilar platformada yo'q)
WORKER = "ijrochi"           # asosiy bo'lim xodimi
ROLES = (BOSS, ASSISTANT, HEAD, WORKER)
MANAGERS = (BOSS, ASSISTANT)         # to'liq huquq: vazifa beradi, qabul qiladi, CRUD qiladi
PERFORMERS = (HEAD, WORKER)          # vazifa oladi va topshiradi

# --- vazifa holatlari ---
NEW = "new"
PROGRESS = "progress"
SUBMITTED = "submitted"
DONE = "done"
CANCELLED = "cancelled"
TASK_STATUSES = (NEW, PROGRESS, SUBMITTED, DONE, CANCELLED)
OPEN_STATUSES = (NEW, PROGRESS)      # eslatma yuboriladigan holatlar

FILE_KINDS = ("task", "proof")       # vazifa bilan berilgan fayl / topshirishdagi dalil
SOURCES = ("web", "bot", "system")
LANGS = ("uz", "ru", "en")


class Department(Base):
    """Tashqi bo'lim. Boshlig'i — `User.department_id` shu bo'limga qaragan `bolim_boshligi`.
    Boshliq alohida ustun emas: bitta haqiqat manbai bo'lsin va aylanma FK bo'lmasin."""
    __tablename__ = "departments"
    id: Mapped[int] = mapped_column(PK, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(150))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(PK, primary_key=True, autoincrement=True)
    full_name: Mapped[str] = mapped_column(String(200))
    login: Mapped[str] = mapped_column(String(64), unique=True)
    phone: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(16), default=WORKER, index=True)
    # Lavozim — erkin matn (Buxgalter, Ta'minotchi...). Hech qanday huquq bermaydi:
    # hisobotda, filtrda va ovozli vazifada odamni topishda ishlatiladi.
    position: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    # Faqat bo'lim boshlig'ida to'ldiriladi. Ijrochida bo'sh — u asosiy bo'lim xodimi.
    department_id: Mapped[Optional[int]] = mapped_column(ForeignKey("departments.id"), nullable=True, index=True)
    lang: Mapped[str] = mapped_column(String(2), default="uz")
    telegram_user_id: Mapped[Optional[int]] = mapped_column(BigInteger, unique=True, nullable=True)
    telegram_linked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    department: Mapped[Optional[Department]] = relationship(lazy="joined")

    @property
    def is_manager(self) -> bool:
        return self.role in MANAGERS


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    id: Mapped[int] = mapped_column(PK, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    token: Mapped[str] = mapped_column(String(128), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)


class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[int] = mapped_column(PK, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    title: Mapped[str] = mapped_column(String(250))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(12), default=NEW, index=True)
    assignee_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    # Muddat sana + soat: "1 soat kechikdi" ni hisoblash uchun soat shart.
    due_at: Mapped[datetime] = mapped_column(DateTime, index=True)

    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    submit_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    done_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    accepted_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    return_count: Mapped[int] = mapped_column(Integer, default=0)
    # Qaytarilgandan keyin eski dalillar hisobga olinmasin — yangi dalil talab qilinadi.
    last_returned_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    due_changed_count: Mapped[int] = mapped_column(Integer, default=0)
    # Vazifa berilgandagi dastlabki muddat — muddat surilsa ham "aslida qachonga edi" qoladi.
    original_due_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    row_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)

    __table_args__ = (
        Index("ix_tasks_assignee_status", "assignee_id", "status"),
        Index("ix_tasks_status_due", "status", "due_at"),
    )

    @property
    def is_open(self) -> bool:
        return self.status in OPEN_STATUSES

    def late_seconds(self, ref: datetime) -> int:
        """Necha soniya kechikkani. Topshirilgan bo'lsa — topshirish vaqtiga qarab o'lchanadi
        (odam vaqtida topshirgan bo'lsa, boss kech qabul qilgani uni kechiktirmaydi)."""
        if self.status == CANCELLED:
            return 0
        end = self.submitted_at or ref
        return max(0, int((end - self.due_at).total_seconds()))


class TaskFile(Base):
    __tablename__ = "task_files"
    id: Mapped[int] = mapped_column(PK, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), index=True)
    kind: Mapped[str] = mapped_column(String(8), default="proof")
    storage_key: Mapped[str] = mapped_column(String(300))
    filename: Mapped[str] = mapped_column(String(250))
    mime_type: Mapped[str] = mapped_column(String(100))
    size: Mapped[int] = mapped_column(BigInteger)
    uploaded_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    source: Mapped[str] = mapped_column(String(8), default="web")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class TaskComment(Base):
    __tablename__ = "task_comments"
    id: Mapped[int] = mapped_column(PK, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), index=True)
    text: Mapped[str] = mapped_column(Text)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    source: Mapped[str] = mapped_column(String(8), default="web")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class TaskHistory(Base):
    __tablename__ = "task_history"
    id: Mapped[int] = mapped_column(PK, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), index=True)
    action: Mapped[str] = mapped_column(String(40))
    old_values_json: Mapped[dict] = mapped_column(JSON, default=dict)
    new_values_json: Mapped[dict] = mapped_column(JSON, default=dict)
    actor_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    source: Mapped[str] = mapped_column(String(8), default="web")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    __table_args__ = (Index("ix_history_task_created", "task_id", "created_at"),)


class Notification(Base):
    """Telegram uchun outbox va eslatmalarning takrorlanmasligini ta'minlaydigan jurnal.

    `dedupe_key` — eslatma dvigatelining kaliti: scheduler har 5 daqiqada ishlaydi, ammo
    "bugungi 09:00 eslatmasi" bir marta yoziladi. Unique cheklov shu ishni bazaga yuklaydi,
    kod tomonda "yubordimmi" degan tekshiruv kerak emas.
    """
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(PK, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    task_id: Mapped[Optional[int]] = mapped_column(ForeignKey("tasks.id"), nullable=True)
    event: Mapped[str] = mapped_column(String(40))
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict)
    channel: Mapped[str] = mapped_column(String(10), default="telegram")
    status: Mapped[str] = mapped_column(String(10), default="pending")   # pending | sent | failed
    dedupe_key: Mapped[Optional[str]] = mapped_column(String(120), unique=True, nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    __table_args__ = (Index("ix_notif_channel_status", "channel", "status"),)


class TelegramLinkCode(Base):
    __tablename__ = "telegram_link_codes"
    code: Mapped[str] = mapped_column(String(6), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    used: Mapped[bool] = mapped_column(Boolean, default=False)


class AppSetting(Base):
    """Kod tegmasdan o'zgaradigan sozlamalar: bot username, eslatma soatlari."""
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)
    updated_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
