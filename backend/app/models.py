from __future__ import annotations

from datetime import datetime, date
from typing import Optional

from sqlalchemy import (
    BigInteger, Boolean, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text,
    UniqueConstraint, func, JSON,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

# SQLite only autoincrements plain INTEGER primary keys; Postgres keeps BIGINT.
PK = BigInteger().with_variant(Integer, "sqlite")

TASK_STATUSES = ("plan", "progress", "review", "done", "blocked", "cancelled")
PRIORITIES = ("low", "normal", "high")
SCOPES = ("system", "project", "location")
SOURCES = ("web", "mobile", "bot", "system")
EVIDENCE_KINDS = ("before", "during", "after", "document")
BLOCK_REASONS = (
    "material_yoq", "hujjat_kutilmoqda", "texnika_band", "ishchi_yetmadi",
    "oldingi_ish", "obhavo", "qaror_kutilmoqda", "boshqa",
)
LANGS = ("uz", "ru", "en")


def now():
    return datetime.utcnow()


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[int] = mapped_column(PK, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Location(Base):
    __tablename__ = "locations"
    id: Mapped[int] = mapped_column(PK, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    parent_id: Mapped[Optional[int]] = mapped_column(ForeignKey("locations.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(10))  # block/floor/zone
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Role(Base):
    __tablename__ = "roles"
    id: Mapped[int] = mapped_column(PK, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    permissions_json: Mapped[list] = mapped_column(JSON, default=list)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(PK, primary_key=True, autoincrement=True)
    full_name: Mapped[str] = mapped_column(String(200))
    login: Mapped[str] = mapped_column(String(64), unique=True)
    phone: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"))
    scope_type: Mapped[str] = mapped_column(String(10), default="system")
    scope_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    lang: Mapped[str] = mapped_column(String(2), default="uz")
    telegram_user_id: Mapped[Optional[int]] = mapped_column(BigInteger, unique=True, nullable=True)
    telegram_linked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    role: Mapped[Role] = relationship(lazy="joined")


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    id: Mapped[int] = mapped_column(PK, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    token: Mapped[str] = mapped_column(String(128), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)


class TaskType(Base):
    __tablename__ = "task_types"
    id: Mapped[int] = mapped_column(PK, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(150))
    group_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    default_duration_days: Mapped[int] = mapped_column(Integer, default=3)
    required_evidence_kinds: Mapped[list] = mapped_column(JSON, default=list)
    default_checklist_json: Mapped[list] = mapped_column(JSON, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class TaskTemplate(Base):
    __tablename__ = "task_templates"
    id: Mapped[int] = mapped_column(PK, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(150))
    type_id: Mapped[int] = mapped_column(ForeignKey("task_types.id"))
    title_pattern: Mapped[str] = mapped_column(String(250))
    default_duration_days: Mapped[int] = mapped_column(Integer, default=3)
    checklist_json: Mapped[list] = mapped_column(JSON, default=list)
    required_evidence_kinds: Mapped[list] = mapped_column(JSON, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[int] = mapped_column(PK, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    location_id: Mapped[Optional[int]] = mapped_column(ForeignKey("locations.id"), nullable=True)
    type_id: Mapped[int] = mapped_column(ForeignKey("task_types.id"))
    title: Mapped[str] = mapped_column(String(250))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(12), default="plan")
    previous_status: Mapped[Optional[str]] = mapped_column(String(12), nullable=True)
    priority: Mapped[str] = mapped_column(String(8), default="normal")
    assignee_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    reviewer_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    planned_start: Mapped[date] = mapped_column(Date)
    planned_end: Mapped[date] = mapped_column(Date)
    actual_start: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    actual_end: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    review_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    progress_percent: Mapped[int] = mapped_column(Integer, default=0)
    planned_quantity: Mapped[Optional[float]] = mapped_column(Numeric(18, 4), nullable=True)
    actual_quantity: Mapped[float] = mapped_column(Numeric(18, 4), default=0)
    unit: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    planned_crew_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    blocked_reason: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    blocked_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    blocked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    return_count: Mapped[int] = mapped_column(Integer, default=0)
    quantity_over_plan: Mapped[bool] = mapped_column(Boolean, default=False)
    template_id: Mapped[Optional[int]] = mapped_column(ForeignKey("task_templates.id"), nullable=True)
    row_version: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    __table_args__ = (
        Index("ix_tasks_project_status", "project_id", "status"),
        Index("ix_tasks_assignee_status", "assignee_id", "status"),
        Index("ix_tasks_reviewer_status", "reviewer_id", "status"),
        Index("ix_tasks_planned_end", "planned_end"),
        Index("ix_tasks_location", "location_id"),
    )


class TaskDependency(Base):
    __tablename__ = "task_dependencies"
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), primary_key=True)
    depends_on_task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), primary_key=True)


class TaskChecklistItem(Base):
    __tablename__ = "task_checklist_items"
    id: Mapped[int] = mapped_column(PK, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), index=True)
    title: Mapped[str] = mapped_column(String(250))
    is_required: Mapped[bool] = mapped_column(Boolean, default=True)
    is_done: Mapped[bool] = mapped_column(Boolean, default=False)
    done_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    done_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class TaskDailyProgress(Base):
    __tablename__ = "task_daily_progress"
    id: Mapped[int] = mapped_column(PK, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"))
    date: Mapped[date] = mapped_column(Date)
    quantity: Mapped[Optional[float]] = mapped_column(Numeric(18, 4), nullable=True)
    workers_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    work_hours: Mapped[Optional[float]] = mapped_column(Numeric(5, 2), nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(8), default="web")
    is_duplicate: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    __table_args__ = (Index("ix_daily_task_date", "task_id", "date"),)


class TaskAttachment(Base):
    __tablename__ = "task_attachments"
    id: Mapped[int] = mapped_column(PK, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), index=True)
    daily_progress_id: Mapped[Optional[int]] = mapped_column(ForeignKey("task_daily_progress.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(10))
    storage_key: Mapped[str] = mapped_column(String(300))
    filename: Mapped[str] = mapped_column(String(250))
    mime_type: Mapped[str] = mapped_column(String(100))
    size: Mapped[int] = mapped_column(BigInteger)
    captured_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    source: Mapped[str] = mapped_column(String(8), default="web")
    uploaded_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class TaskComment(Base):
    __tablename__ = "task_comments"
    id: Mapped[int] = mapped_column(PK, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), index=True)
    text: Mapped[str] = mapped_column(Text)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    mentions_json: Mapped[list] = mapped_column(JSON, default=list)
    source: Mapped[str] = mapped_column(String(8), default="web")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    edited_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class TaskHistory(Base):
    __tablename__ = "task_history"
    id: Mapped[int] = mapped_column(PK, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"))
    action: Mapped[str] = mapped_column(String(40))
    old_values_json: Mapped[dict] = mapped_column(JSON, default=dict)
    new_values_json: Mapped[dict] = mapped_column(JSON, default=dict)
    actor_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    source: Mapped[str] = mapped_column(String(8), default="web")
    request_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    __table_args__ = (Index("ix_history_task_created", "task_id", "created_at"),)


class TaskRecurringRule(Base):
    __tablename__ = "task_recurring_rules"
    id: Mapped[int] = mapped_column(PK, primary_key=True, autoincrement=True)
    template_id: Mapped[int] = mapped_column(ForeignKey("task_templates.id"))
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    location_id: Mapped[Optional[int]] = mapped_column(ForeignKey("locations.id"), nullable=True)
    assignee_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    reviewer_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    rrule: Mapped[str] = mapped_column(String(120))  # FREQ=DAILY | FREQ=WEEKLY;BYDAY=MO,WE,FR
    next_run_at: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(PK, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    task_id: Mapped[Optional[int]] = mapped_column(ForeignKey("tasks.id"), nullable=True)
    event: Mapped[str] = mapped_column(String(40))
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict)
    channel: Mapped[str] = mapped_column(String(10))  # inapp | telegram
    status: Mapped[str] = mapped_column(String(10), default="pending")  # pending sent failed
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
    """Kod tegmasdan o'zgaradigan sozlamalar (masalan bot username)."""
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)
    updated_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(PK, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(12), default="queued")
    total: Mapped[int] = mapped_column(Integer, default=0)
    done: Mapped[int] = mapped_column(Integer, default=0)
    result_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
