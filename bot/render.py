"""Render task cards / keyboards."""
from __future__ import annotations

from datetime import date

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import settings
from i18n import t, status_label, prio_label, block_label, STATUS_ICON


def fmt_date(s) -> str:
    if not s:
        return "—"
    try:
        d = date.fromisoformat(str(s)[:10])
        return d.strftime("%d.%m")
    except Exception:
        return str(s)


def loc_str(task: dict) -> str:
    path = task.get("location_path") or []
    s = " · ".join(p["name"] for p in path)
    return s or task.get("project_name") or "—"


def task_card(lang: str, tk: dict) -> str:
    ov = ""
    if tk.get("overdue_days"):
        ov = "  " + t(lang, "overdue", d=tk["overdue_days"])
    blocked = t(lang, "blocked_line", reason=block_label(lang, tk.get("blocked_reason")), note=tk.get("blocked_note") or "") if tk.get("status") == "blocked" else ""
    deps = t(lang, "deps_line", codes=", ".join(tk["dependency_pending"])) if tk.get("dependency_pending") else ""
    ret = t(lang, "ret_line", n=tk["return_count"]) if tk.get("return_count") else ""
    return t(lang, "task_card", icon=STATUS_ICON.get(tk["status"], "▫️"), code=tk["code"], status=status_label(lang, tk["status"]),
             title=tk["title"], loc=loc_str(tk), assignee=tk.get("assignee_name") or "—", reviewer=tk.get("reviewer_name") or "—",
             start=fmt_date(tk["planned_start"]), end=fmt_date(tk["planned_end"]), overdue=ov,
             ck_done=tk.get("checklist_done", 0), ck_total=tk.get("checklist_total", 0), photos=tk.get("photos_count", 0),
             progress=tk.get("progress_percent", 0), blocked=blocked, deps=deps, ret=ret)


def task_kb(lang: str, tk: dict) -> InlineKeyboardMarkup:
    p = tk.get("permissions") or {}
    tid = tk["id"]
    b = InlineKeyboardBuilder()
    row = []
    if p.get("start"):
        row.append(InlineKeyboardButton(text=t(lang, "a_start"), callback_data=f"t:start:{tid}"))
    if p.get("submit_review"):
        row.append(InlineKeyboardButton(text=t(lang, "a_review"), callback_data=f"t:review:{tid}"))
    if p.get("accept"):
        row.append(InlineKeyboardButton(text=t(lang, "a_accept"), callback_data=f"t:accept:{tid}"))
    if p.get("return"):
        row.append(InlineKeyboardButton(text=t(lang, "a_return"), callback_data=f"t:return:{tid}"))
    if row:
        b.row(*row)
    row = []
    if p.get("progress"):
        row.append(InlineKeyboardButton(text=t(lang, "a_report"), callback_data=f"t:report:{tid}"))
    if p.get("checklist") and tk.get("checklist_total"):
        row.append(InlineKeyboardButton(text=t(lang, "a_checklist"), callback_data=f"t:ck:{tid}"))
    if p.get("block"):
        row.append(InlineKeyboardButton(text=t(lang, "a_block"), callback_data=f"t:block:{tid}"))
    if p.get("unblock"):
        row.append(InlineKeyboardButton(text=t(lang, "a_unblock"), callback_data=f"t:unblock:{tid}"))
    if row:
        b.row(*row)
    row = [InlineKeyboardButton(text=t(lang, "a_comment"), callback_data=f"t:comment:{tid}"),
           InlineKeyboardButton(text=t(lang, "a_refresh"), callback_data=f"t:show:{tid}")]
    if settings.WEB_URL:
        row.append(InlineKeyboardButton(text=t(lang, "a_open"), url=f"{settings.WEB_URL.rstrip('/')}/tasks/{tid}"))
    b.row(*row)
    return b.as_markup()


def tasks_list_kb(lang: str, tasks: list[dict]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for tk in tasks[:20]:
        icon = STATUS_ICON.get(tk["status"], "▫️")
        late = f" ⏱{tk['overdue_days']}" if tk.get("overdue_days") else ""
        b.row(InlineKeyboardButton(text=f"{icon} {tk['code']} · {tk['title'][:40]}{late}", callback_data=f"t:show:{tk['id']}"))
    return b.as_markup()


def checklist_kb(lang: str, tk: dict) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for it in tk.get("checklist", []):
        mark = "☑️" if it["is_done"] else "⬜"
        req = "*" if it["is_required"] else ""
        b.row(InlineKeyboardButton(text=f"{mark} {it['title'][:50]}{req}", callback_data=f"ck:{tk['id']}:{it['id']}:{0 if it['is_done'] else 1}"))
    b.row(InlineKeyboardButton(text=t(lang, "btn_back"), callback_data=f"t:show:{tk['id']}"))
    return b.as_markup()


# menu button -> (permission it needs [None = everyone], roles that never see it even with the permission)
# "admin" (superadmin/IT egasi) faqat kuzatadi va vazifa beradi - o'zi hech qachon ijrochi yoki
# tekshiruvchi bo'lmaydi (default_reviewer ham admin'ni hech qachon tanlamaydi), shuning uchun
# "o'z vazifangni bajarish" tugmalari (Vazifalarim/Kunlik hisobot/Muammo/Tekshiruv) unga ko'rsatilmaydi -
# aks holda doim bo'sh ro'yxatga olib boradi va chalkashtiradi.
MENU = [
    ("btn_my", None, {"admin", "kuzatuvchi"}),
    ("btn_report", "progress.create", {"admin"}),
    ("btn_review", "tasks.accept", {"admin"}),
    ("btn_new", "tasks.create", set()),
    ("btn_problem", "tasks.block", {"admin"}),
    ("btn_overdue", "reports.read", set()),
    ("btn_blocked", "reports.read", set()),
    ("btn_reports", "reports.read", set()),
    ("btn_team", "admin.users", set()),
    ("btn_search", None, set()),
    ("btn_lang", None, set()),
    ("btn_help", None, set()),
]


def menu_keys(lang: str, perms: set[str], role: str | None = None) -> list[str]:
    return [t(lang, k) for k, need, hide_for in MENU if (need is None or need in perms) and role not in hide_for]


def main_menu(lang: str, perms: set[str], role: str | None = None) -> ReplyKeyboardMarkup:
    """The keyboard is built from the user's own permissions - each role gets its own bot."""
    keys = menu_keys(lang, perms, role)
    rows = [[KeyboardButton(text=k) for k in keys[i:i + 2]] for i in range(0, len(keys), 2)]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, is_persistent=True)


def cancel_kb(lang: str, skip: bool = False, done: bool = False) -> ReplyKeyboardMarkup:
    row = []
    if done:
        row.append(KeyboardButton(text=t(lang, "btn_done")))
    if skip:
        row.append(KeyboardButton(text=t(lang, "btn_skip")))
    row.append(KeyboardButton(text=t(lang, "btn_cancel")))
    return ReplyKeyboardMarkup(keyboard=[row], resize_keyboard=True)


def confirm_card(lang: str, d: dict, names: dict) -> str:
    voice = t(lang, "voice_head", text=d["transcript"][:300]) if d.get("transcript") else ""
    warn = ""
    if not d.get("project_id"):
        warn += t(lang, "no_project_warn")
    if not d.get("assignee_id"):
        if d.get("assignee_candidates"):
            warn += t(lang, "ambiguous_assignee", heard=d.get("assignee_name_heard") or "?")
        else:
            warn += t(lang, "no_assignee_warn")
    if "no_deadline" in (d.get("warnings") or []):
        warn += t(lang, "no_deadline_warn")
    desc = f"\n📝 {d['description'][:200]}" if d.get("description") else ""
    return t(lang, "confirm_card", voice=voice, title=d.get("title") or "—",
             assignee=names.get("assignee") or t(lang, "not_set"),
             reviewer=names.get("reviewer") or t(lang, "not_set"), start=fmt_date(d.get("planned_start")),
             end=fmt_date(d.get("planned_end")), prio=prio_label(lang, d.get("priority") or "normal"),
             project=names.get("project") or t(lang, "not_set"), loc=names.get("location") or t(lang, "not_set"),
             type=names.get("type") or t(lang, "not_set"), desc=desc, warn=warn)


def confirm_kb(lang: str, d: dict) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if not d.get("assignee_id") and d.get("assignee_candidates"):
        for c in d["assignee_candidates"][:3]:
            # bir xil ismli ikki odam bo'lsa hint ("Prorab · B blok") ularni ajratib turadi
            hint = f" · {c['hint']}" if c.get("hint") else ""
            b.row(InlineKeyboardButton(text=f"👤 {c['full_name']}{hint} ({c['score']}%)"[:64],
                                       callback_data=f"nt:pick_a:{c['id']}"))
        b.row(InlineKeyboardButton(text=t(lang, "other_person"), callback_data="nt:edit:assignee"))
    ready = bool(d.get("assignee_id") and d.get("project_id") and d.get("title") and d.get("type_id"))
    row = []
    if ready:
        row.append(InlineKeyboardButton(text=t(lang, "c_send"), callback_data="nt:send"))
    row.append(InlineKeyboardButton(text=t(lang, "c_edit"), callback_data="nt:edit"))
    row.append(InlineKeyboardButton(text=t(lang, "c_cancel"), callback_data="nt:cancel"))
    b.row(*row)
    return b.as_markup()


def edit_menu_kb(lang: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text=t(lang, "e_title"), callback_data="nt:edit:title"),
          InlineKeyboardButton(text=t(lang, "e_assignee"), callback_data="nt:edit:assignee"))
    b.row(InlineKeyboardButton(text=t(lang, "e_reviewer"), callback_data="nt:edit:reviewer"))
    b.row(InlineKeyboardButton(text=t(lang, "e_deadline"), callback_data="nt:edit:deadline"),
          InlineKeyboardButton(text=t(lang, "e_prio"), callback_data="nt:edit:prio"))
    b.row(InlineKeyboardButton(text=t(lang, "e_project"), callback_data="nt:edit:project"),
          InlineKeyboardButton(text=t(lang, "e_loc"), callback_data="nt:edit:loc"))
    b.row(InlineKeyboardButton(text=t(lang, "e_type"), callback_data="nt:edit:type"),
          InlineKeyboardButton(text=t(lang, "e_desc"), callback_data="nt:edit:desc"))
    b.row(InlineKeyboardButton(text=t(lang, "btn_back"), callback_data="nt:back"))
    return b.as_markup()


def deadline_kb(lang: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text=t(lang, "d_today"), callback_data="nt:dl:0"),
          InlineKeyboardButton(text=t(lang, "d_tomorrow"), callback_data="nt:dl:1"),
          InlineKeyboardButton(text=t(lang, "d_3"), callback_data="nt:dl:3"))
    b.row(InlineKeyboardButton(text=t(lang, "d_week"), callback_data="nt:dl:7"),
          InlineKeyboardButton(text=t(lang, "d_2w"), callback_data="nt:dl:14"),
          InlineKeyboardButton(text=t(lang, "d_month"), callback_data="nt:dl:eom"))
    b.row(InlineKeyboardButton(text=t(lang, "d_custom"), callback_data="nt:dl:custom"))
    return b.as_markup()


def prio_kb(lang: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🟢 " + prio_label(lang, "low"), callback_data="nt:prio:low"),
          InlineKeyboardButton(text="🟡 " + prio_label(lang, "normal"), callback_data="nt:prio:normal"),
          InlineKeyboardButton(text="🔴 " + prio_label(lang, "high"), callback_data="nt:prio:high"))
    return b.as_markup()


def list_kb(items: list[dict], prefix: str, label_key: str = "name", page: int = 0, per: int = 8,
            extra: list[InlineKeyboardButton] | None = None, skip_cb: str | None = None, skip_text: str = "⏭") -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    chunk = items[page * per:(page + 1) * per]
    for it in chunk:
        b.row(InlineKeyboardButton(text=str(it[label_key])[:48], callback_data=f"{prefix}:{it['id']}"))
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️", callback_data=f"{prefix}_pg:{page - 1}"))
    if (page + 1) * per < len(items):
        nav.append(InlineKeyboardButton(text="▶️", callback_data=f"{prefix}_pg:{page + 1}"))
    if nav:
        b.row(*nav)
    if skip_cb:
        b.row(InlineKeyboardButton(text=skip_text, callback_data=skip_cb))
    if extra:
        b.row(*extra)
    return b.as_markup()


def block_reasons_kb(lang: str, tid: int) -> InlineKeyboardMarkup:
    from i18n import BLOCK
    b = InlineKeyboardBuilder()
    codes = list(BLOCK["uz"].keys())
    for i in range(0, len(codes), 2):
        b.row(*[InlineKeyboardButton(text=block_label(lang, c), callback_data=f"blk:{tid}:{c}") for c in codes[i:i + 2]])
    return b.as_markup()


def lang_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🇺🇿 O'zbekcha", callback_data="lang:uz"),
          InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang:ru"),
          InlineKeyboardButton(text="🇬🇧 English", callback_data="lang:en"))
    return b.as_markup()
