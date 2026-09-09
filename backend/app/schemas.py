from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from .models import FILE_KINDS, LANGS, ROLES, TASK_STATUSES


class Model(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- auth ----------
class LoginIn(BaseModel):
    login: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int
    user: "UserOut"


class RefreshIn(BaseModel):
    refresh_token: str


class PasswordIn(BaseModel):
    password: str = Field(min_length=1, max_length=100)


class MeIn(BaseModel):
    full_name: Optional[str] = Field(default=None, max_length=200)
    phone: Optional[str] = Field(default=None, max_length=32)
    lang: Optional[Literal["uz", "ru", "en"]] = None
    password: Optional[str] = Field(default=None, max_length=100)


# ---------- departments ----------
class DepartmentIn(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    sort_order: int = 0


class DepartmentOut(Model):
    id: int
    name: str
    sort_order: int
    is_active: bool
    head_id: Optional[int] = None
    head_name: Optional[str] = None
    open_tasks: int = 0
    late_tasks: int = 0


# ---------- users ----------
class UserIn(BaseModel):
    full_name: str = Field(min_length=1, max_length=200)
    login: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=1, max_length=100)
    role: Literal["boss", "assistant", "bolim_boshligi", "ijrochi"]
    position: Optional[str] = Field(default=None, max_length=100)
    phone: Optional[str] = Field(default=None, max_length=32)
    department_id: Optional[int] = None
    lang: Literal["uz", "ru", "en"] = "uz"


class UserPatch(BaseModel):
    full_name: Optional[str] = Field(default=None, max_length=200)
    login: Optional[str] = Field(default=None, min_length=2, max_length=64)
    role: Optional[Literal["boss", "assistant", "bolim_boshligi", "ijrochi"]] = None
    position: Optional[str] = Field(default=None, max_length=100)
    phone: Optional[str] = Field(default=None, max_length=32)
    department_id: Optional[int] = None
    lang: Optional[Literal["uz", "ru", "en"]] = None
    is_active: Optional[bool] = None


class UserOut(Model):
    id: int
    full_name: str
    login: str
    role: str
    role_name: str = ""
    position: Optional[str] = None
    phone: Optional[str] = None
    department_id: Optional[int] = None
    department_name: Optional[str] = None
    lang: str
    telegram_user_id: Optional[int] = None
    is_active: bool
    open_tasks: int = 0
    late_tasks: int = 0


# ---------- tasks ----------
class TaskIn(BaseModel):
    title: str = Field(min_length=1, max_length=250)
    assignee_id: int
    due_at: str                      # "2026-09-10" (-> 18:00) yoki "2026-09-10T14:00"
    description: Optional[str] = Field(default=None, max_length=4000)


class TaskPatch(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=250)
    assignee_id: Optional[int] = None
    due_at: Optional[str] = None
    description: Optional[str] = Field(default=None, max_length=4000)
    row_version: Optional[int] = None


class SubmitIn(BaseModel):
    note: str = Field(min_length=1, max_length=2000)
    file_ids: list[int] = Field(default_factory=list)


class ReasonIn(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)


class CommentIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class FileOut(Model):
    id: int
    kind: str
    filename: str
    mime_type: str
    size: int
    url: Optional[str] = None
    created_at: datetime


class CommentOut(Model):
    id: int
    text: str
    author_id: int
    author_name: str = ""
    created_at: datetime


class HistoryOut(Model):
    id: int
    action: str
    actor_id: Optional[int] = None
    actor_name: str = ""
    old_values_json: dict = {}
    new_values_json: dict = {}
    created_at: datetime


class TaskOut(Model):
    id: int
    code: str
    title: str
    description: Optional[str] = None
    status: str
    assignee_id: int
    assignee_name: str = ""
    assignee_role: str = ""
    department_id: Optional[int] = None
    department_name: Optional[str] = None
    created_by: int
    created_by_name: str = ""
    due_at: datetime
    original_due_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    submitted_at: Optional[datetime] = None
    submit_note: Optional[str] = None
    done_at: Optional[datetime] = None
    accepted_by: Optional[int] = None
    accepted_by_name: Optional[str] = None
    return_count: int = 0
    due_changed_count: int = 0
    row_version: int = 1
    created_at: datetime
    # hisoblanadigan
    is_late: bool = False
    late_days: int = 0
    late_hours: int = 0
    proof_count: int = 0
    comment_count: int = 0
    permissions: dict = {}
    files: list[FileOut] = []
    comments: list[CommentOut] = []


class TaskListOut(BaseModel):
    items: list[TaskOut]
    total: int
    page: int
    per_page: int


# ---------- reports ----------
class PersonStat(BaseModel):
    user_id: int
    full_name: str
    role: str
    position: Optional[str] = None
    department_id: Optional[int] = None
    department_name: Optional[str] = None
    given: int = 0
    on_time: int = 0
    late_done: int = 0
    not_done: int = 0
    in_progress: int = 0
    returned: int = 0
    avg_late_days: float = 0.0
    percent: float = 0.0


class ReportOut(BaseModel):
    period: str
    date_from: date
    date_to: date
    rows: list[PersonStat]
    totals: PersonStat


class DashboardOut(BaseModel):
    open_tasks: int
    late_tasks: int
    submitted_tasks: int
    due_today: int
    done_this_month: int
    percent_this_month: float
    people: int
    departments: int


# ---------- misc ----------
class MetaOut(BaseModel):
    roles: list[dict[str, Any]]
    statuses: list[str]
    bot_username: Optional[str] = None
    reminder_hours: list[int] = []


class LinkCodeOut(BaseModel):
    code: str
    expires_at: datetime
    deep_link: Optional[str] = None


class ConsumeCodeIn(BaseModel):
    code: str
    telegram_user_id: int


class OutboxAckIn(BaseModel):
    sent: list[int] = []
    failed: list[int] = []


class ParseTaskIn(BaseModel):
    text: str
    lang: str = "uz"


class ParsedTask(BaseModel):
    transcript: Optional[str] = None
    title: str
    description: Optional[str] = None
    due_at: Optional[str] = None
    assignee_id: Optional[int] = None
    assignee_name_heard: Optional[str] = None
    assignee_candidates: list[dict] = []
    warnings: list[str] = []


TokenOut.model_rebuild()

__all__ = [n for n in dir() if n[0].isupper()] + ["FILE_KINDS", "LANGS", "ROLES", "TASK_STATUSES"]
