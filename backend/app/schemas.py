from __future__ import annotations

from datetime import date, datetime
from typing import Optional, Any, Generic, TypeVar, List

from pydantic import BaseModel, Field, ConfigDict

T = TypeVar("T")


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):
    items: List[T]
    total: int
    limit: int
    offset: int


# ---- auth ----
class LoginIn(BaseModel):
    login: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshIn(BaseModel):
    refresh_token: str


class RoleOut(ORM):
    id: int
    code: str
    name: str
    permissions_json: list
    is_system: bool


class UserBrief(ORM):
    id: int
    full_name: str
    login: str
    is_active: bool = True


class UserOut(UserBrief):
    phone: Optional[str] = None
    email: Optional[str] = None
    role_id: int
    role: RoleOut
    scope_type: str
    scope_id: Optional[int] = None
    lang: str = "uz"
    telegram_user_id: Optional[int] = None
    telegram_linked_at: Optional[datetime] = None
    last_login_at: Optional[datetime] = None
    created_at: datetime


class MeOut(BaseModel):
    user: UserOut
    permissions: List[str]
    scope: dict


class UserCreate(BaseModel):
    full_name: str
    login: str
    password: str
    phone: Optional[str] = None
    email: Optional[str] = None
    role_id: int
    scope_type: str = "system"
    scope_id: Optional[int] = None
    lang: str = "uz"


class UserPatch(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    role_id: Optional[int] = None
    scope_type: Optional[str] = None
    scope_id: Optional[int] = None
    lang: Optional[str] = None
    password: Optional[str] = None
    is_active: Optional[bool] = None


class RoleIn(BaseModel):
    code: Optional[str] = None
    name: Optional[str] = None
    permissions_json: Optional[list] = None


# ---- projects / locations ----
class ProjectOut(ORM):
    id: int
    code: str
    name: str
    is_active: bool
    created_at: datetime


class ProjectIn(BaseModel):
    code: Optional[str] = None
    name: Optional[str] = None
    is_active: Optional[bool] = None


class LocationOut(ORM):
    id: int
    project_id: int
    parent_id: Optional[int]
    name: str
    kind: str
    sort_order: int
    is_active: bool


class LocationIn(BaseModel):
    project_id: Optional[int] = None
    parent_id: Optional[int] = None
    name: Optional[str] = None
    kind: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


# ---- task types / templates ----
class ChecklistTpl(BaseModel):
    title: str
    is_required: bool = True
    sort_order: int = 0


class TaskTypeOut(ORM):
    id: int
    name: str
    group_name: Optional[str]
    default_duration_days: int
    required_evidence_kinds: list
    default_checklist_json: list
    is_active: bool


class TaskTypeIn(BaseModel):
    name: Optional[str] = None
    group_name: Optional[str] = None
    default_duration_days: Optional[int] = None
    required_evidence_kinds: Optional[list] = None
    default_checklist_json: Optional[list] = None
    is_active: Optional[bool] = None


class TemplateOut(ORM):
    id: int
    name: str
    type_id: int
    title_pattern: str
    default_duration_days: int
    checklist_json: list
    required_evidence_kinds: list
    is_active: bool


class TemplateIn(BaseModel):
    name: Optional[str] = None
    type_id: Optional[int] = None
    title_pattern: Optional[str] = None
    default_duration_days: Optional[int] = None
    checklist_json: Optional[list] = None
    required_evidence_kinds: Optional[list] = None
    is_active: Optional[bool] = None


class InstantiateIn(BaseModel):
    project_id: int
    location_id: Optional[int] = None
    assignee_id: int
    reviewer_id: int
    planned_start: date
    variables: dict = {}
    priority: str = "normal"


# ---- tasks ----
class ChecklistItemOut(ORM):
    id: int
    title: str
    is_required: bool
    is_done: bool
    done_by: Optional[int]
    done_at: Optional[datetime]
    sort_order: int


class LocationPath(BaseModel):
    id: int
    name: str
    kind: str


class TaskCard(ORM):
    id: int
    code: str
    project_id: int
    location_id: Optional[int]
    type_id: int
    title: str
    status: str
    previous_status: Optional[str]
    priority: str
    assignee_id: int
    reviewer_id: int
    planned_start: date
    planned_end: date
    actual_start: Optional[datetime]
    actual_end: Optional[datetime]
    review_started_at: Optional[datetime]
    progress_percent: int
    planned_quantity: Optional[float]
    actual_quantity: float
    unit: Optional[str]
    blocked_reason: Optional[str]
    blocked_note: Optional[str]
    blocked_at: Optional[datetime]
    return_count: int
    quantity_over_plan: bool
    row_version: int
    created_at: datetime
    updated_at: datetime
    # enriched
    assignee_name: str = ""
    reviewer_name: str = ""
    type_name: str = ""
    project_name: str = ""
    location_path: List[LocationPath] = []
    checklist_done: int = 0
    checklist_total: int = 0
    photos_count: int = 0
    overdue_days: int = 0
    review_days: int = 0
    blocked_days: int = 0
    dependency_pending: List[str] = []


class TaskDetail(TaskCard):
    description: Optional[str]
    planned_crew_size: Optional[int]
    template_id: Optional[int]
    created_by: int
    checklist: List[ChecklistItemOut] = []
    dependencies: List[dict] = []
    dependents: List[dict] = []
    attachments: List[AttachmentOut] = []
    permissions: dict = {}
    required_evidence_kinds: list = []


class TaskCreate(BaseModel):
    project_id: int
    location_id: Optional[int] = None
    type_id: int
    title: str = Field(min_length=2, max_length=250)
    description: Optional[str] = None
    priority: str = "normal"
    assignee_id: int
    reviewer_id: int
    planned_start: date
    planned_end: date
    planned_quantity: Optional[float] = None
    unit: Optional[str] = None
    planned_crew_size: Optional[int] = None
    checklist: Optional[List[ChecklistTpl]] = None  # None => from type default
    depends_on: List[int] = []
    template_id: Optional[int] = None


class TaskPatch(BaseModel):
    row_version: int
    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[str] = None
    assignee_id: Optional[int] = None
    reviewer_id: Optional[int] = None
    planned_start: Optional[date] = None
    planned_end: Optional[date] = None
    planned_quantity: Optional[float] = None
    unit: Optional[str] = None
    planned_crew_size: Optional[int] = None
    location_id: Optional[int] = None
    type_id: Optional[int] = None
    date_change_reason: Optional[str] = None


class TransitionIn(BaseModel):
    to: str
    note: Optional[str] = None


class NoteIn(BaseModel):
    """Optional body for accept / reopen — every field optional so `{}` is valid."""
    note: Optional[str] = None


class BlockIn(BaseModel):
    reason: str
    note: str = Field(min_length=2)


class ReturnIn(BaseModel):
    reason: str = Field(min_length=2)


class ChecklistBulk(BaseModel):
    items: List[dict]  # [{id, is_done}]


class ChecklistAdd(BaseModel):
    title: str
    is_required: bool = False


class DailyIn(BaseModel):
    date: date
    quantity: Optional[float] = None
    workers_count: Optional[int] = None
    work_hours: Optional[float] = None
    note: Optional[str] = None


class DailyOut(ORM):
    id: int
    task_id: int
    date: date
    quantity: Optional[float]
    workers_count: Optional[int]
    work_hours: Optional[float]
    note: Optional[str]
    source: str
    is_duplicate: bool
    created_by: int
    created_at: datetime
    created_by_name: str = ""


class AttachmentOut(ORM):
    id: int
    task_id: int
    daily_progress_id: Optional[int]
    kind: str
    filename: str
    mime_type: str
    size: int
    captured_at: Optional[datetime]
    source: str
    uploaded_by: int
    created_at: datetime
    url: str = ""
    uploaded_by_name: str = ""


class CommentIn(BaseModel):
    text: str = Field(min_length=1)


class CommentOut(ORM):
    id: int
    task_id: int
    text: str
    author_id: int
    mentions_json: list
    source: str
    created_at: datetime
    edited_at: Optional[datetime]
    author_name: str = ""


class HistoryOut(ORM):
    id: int
    action: str
    old_values_json: dict
    new_values_json: dict
    actor_id: Optional[int]
    source: str
    request_id: Optional[str]
    created_at: datetime
    actor_name: str = ""


class DependencyIn(BaseModel):
    depends_on_task_id: int


class BulkCopyIn(BaseModel):
    source_location_id: int
    target_location_ids: List[int]
    date_step_days: int = 0
    assignee_policy: str = "keep"      # keep | user:<id>
    dependency_policy: str = "none"    # none | chain
    as_draft: bool = True
    dry_run: bool = True


class RecurringOut(ORM):
    id: int
    template_id: int
    project_id: int
    location_id: Optional[int]
    assignee_id: int
    reviewer_id: int
    rrule: str
    next_run_at: Optional[date]
    is_active: bool


class RecurringIn(BaseModel):
    template_id: Optional[int] = None
    project_id: Optional[int] = None
    location_id: Optional[int] = None
    assignee_id: Optional[int] = None
    reviewer_id: Optional[int] = None
    rrule: Optional[str] = None
    is_active: Optional[bool] = None


class NotificationOut(ORM):
    id: int
    task_id: Optional[int]
    event: str
    payload_json: dict
    channel: str
    status: str
    is_read: bool
    created_at: datetime


class LinkCodeOut(BaseModel):
    code: str
    expires_at: datetime
    bot_username: Optional[str] = None


# ---- AI ----
class ParseTaskIn(BaseModel):
    text: str
    project_id: Optional[int] = None
    lang: str = "uz"


class Candidate(BaseModel):
    id: int
    full_name: str
    role: str
    score: int
    # bir xil ismli ikki odamni ajratish uchun: "Prorab · B blok" kabi
    hint: Optional[str] = None


class ParsedTask(BaseModel):
    transcript: str
    title: str
    description: Optional[str] = None
    priority: str = "normal"
    planned_start: Optional[date] = None
    planned_end: Optional[date] = None
    project_id: Optional[int] = None
    project_name: Optional[str] = None
    location_id: Optional[int] = None
    location_name: Optional[str] = None
    type_id: Optional[int] = None
    type_name: Optional[str] = None
    assignee_id: Optional[int] = None
    assignee_name_heard: Optional[str] = None
    assignee_candidates: List[Candidate] = []
    assignee_confident: bool = False
    reviewer_id: Optional[int] = None
    warnings: List[str] = []


TaskDetail.model_rebuild()
