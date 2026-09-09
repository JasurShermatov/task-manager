"""Kartochkalar va tugmalar."""
from __future__ import annotations

from datetime import datetime

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from i18n import STATUS_ICON, T, field_label, role_label, status_label, t

try:  # Bot API 7.11 / aiogram 3.15+ — bir bosishda matnni nusxa oladi
    from aiogram.types import CopyTextButton
except ImportError:  # eski aiogram: <pre> blokini bosib nusxa olinadi
    CopyTextButton = None

COPY_LIMIT = 256
MANAGERS = ("boss", "assistant")

# Menyu: (kalit, faqat boshqaruvchigami)
MENU = [
    ("btn_new", True), ("btn_submitted", True), ("btn_late", True),
    ("btn_report", True), ("btn_people", True),
    ("btn_my", False), ("btn_submit", False),
    ("btn_lang", None),          # None - hammaga
]


def menu_keys(lang: str, role: str) -> list[str]:
    mgr = role in MANAGERS
    return [t(lang, k) for k, need in MENU if need is None or need == mgr]


def main_menu(lang: str, role: str) -> ReplyKeyboardMarkup:
    keys = menu_keys(lang, role)
    rows, row = [], []
    for k in keys:
        row.append(KeyboardButton(text=k))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def cancel_kb(lang: str, done: bool = False) -> ReplyKeyboardMarkup:
    row = []
    if done:
        row.append(KeyboardButton(text=t(lang, "btn_done")))
    row.append(KeyboardButton(text=t(lang, "btn_cancel")))
    return ReplyKeyboardMarkup(keyboard=[row], resize_keyboard=True)


# ---------------------------------------------------------------- sana
def fmt_due(value, lang: str = "uz") -> str:
    """«10.09.2026 18:00». Soat 18:00 bo'lsa ham ko'rsatiladi — muddat aniq bo'lsin."""
    if not value:
        return "—"
    try:
        d = datetime.fromisoformat(str(value)[:19])
    except ValueError:
        return str(value)
    return d.strftime("%d.%m.%Y %H:%M")


def fmt_day(value) -> str:
    if not value:
        return "—"
    try:
        return datetime.fromisoformat(str(value)[:19]).strftime("%d.%m.%Y")
    except ValueError:
        return str(value)


def late_text(lang: str, days: int, hours: int) -> str:
    if days > 0:
        return t(lang, "late_d", d=days)
    return t(lang, "late_h", h=max(1, hours))


# ---------------------------------------------------------------- vazifa kartochkasi
def task_card(lang: str, tk: dict) -> str:
    late = ""
    if tk.get("is_late"):
        late = (t(lang, "late_mark", days=tk["late_days"]) if tk.get("late_days")
                else t(lang, "late_hours_mark", hours=max(1, tk.get("late_hours", 1))))
    extra = ""
    if tk.get("return_count"):
        extra += t(lang, "returned_mark", n=tk["return_count"])
    if tk.get("description"):
        extra += t(lang, "desc_line", text=tk["description"][:300])
    if tk.get("submit_note"):
        extra += t(lang, "note_line", note=tk["submit_note"][:300])
    if tk.get("proof_count"):
        extra += t(lang, "proof_line", n=tk["proof_count"])
    return t(lang, "task_card", icon=STATUS_ICON.get(tk["status"], "▫️"), code=tk["code"],
             status=status_label(lang, tk["status"]), title=tk["title"],
             assignee=tk.get("assignee_name") or "—", due=fmt_due(tk.get("due_at"), lang),
             late=late, extra=extra)


def task_kb(lang: str, tk: dict) -> InlineKeyboardMarkup | None:
    p = tk.get("permissions") or {}
    tid = tk["id"]
    b = InlineKeyboardBuilder()
    row = []
    if p.get("start"):
        row.append(InlineKeyboardButton(text=t(lang, "a_start"), callback_data=f"t:start:{tid}"))
    if p.get("submit"):
        row.append(InlineKeyboardButton(text=t(lang, "a_submit"), callback_data=f"t:sub:{tid}"))
    if p.get("accept"):
        row.append(InlineKeyboardButton(text=t(lang, "a_accept"), callback_data=f"t:acc:{tid}"))
    if p.get("return"):
        row.append(InlineKeyboardButton(text=t(lang, "a_return"), callback_data=f"t:ret:{tid}"))
    if row:
        b.row(*row)
    b.row(InlineKeyboardButton(text=t(lang, "a_comment"), callback_data=f"t:cm:{tid}"))
    return b.as_markup()


def list_kb(items: list[dict], prefix: str, label_key: str = "name", page: int = 0, per: int = 8,
            extra: list[InlineKeyboardButton] | None = None) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for it in items[page * per:(page + 1) * per]:
        b.row(InlineKeyboardButton(text=str(it[label_key])[:60], callback_data=f"{prefix}:{it['id']}"))
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️", callback_data=f"{prefix}_pg:{page - 1}"))
    if (page + 1) * per < len(items):
        nav.append(InlineKeyboardButton(text="▶️", callback_data=f"{prefix}_pg:{page + 1}"))
    if nav:
        b.row(*nav)
    for x in extra or []:
        b.row(x)
    return b.as_markup()


# ---------------------------------------------------------------- yangi vazifa
def confirm_card(lang: str, d: dict) -> str:
    voice = t(lang, "voice_head", text=d["transcript"][:300]) if d.get("transcript") else ""
    warn = ""
    if not d.get("assignee_id"):
        warn += (t(lang, "ambiguous_assignee", heard=d.get("assignee_name_heard") or "?")
                 if d.get("assignee_candidates") else t(lang, "no_assignee_warn"))
    if not d.get("due_at"):
        warn += t(lang, "no_due_warn")
    desc = t(lang, "desc_line", text=d["description"][:300]) if d.get("description") else ""
    return t(lang, "confirm_card", voice=voice, title=d.get("title") or "—",
             assignee=d.get("assignee_name") or t(lang, "not_set"),
             due=fmt_due(d.get("due_at"), lang) if d.get("due_at") else t(lang, "not_set"),
             desc=desc, warn=warn)


def confirm_kb(lang: str, d: dict) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if not d.get("assignee_id") and d.get("assignee_candidates"):
        for c in d["assignee_candidates"][:3]:
            hint = f" · {c['hint']}" if c.get("hint") else ""
            b.row(InlineKeyboardButton(text=f"👤 {c['full_name']}{hint} ({c['score']}%)"[:64],
                                       callback_data=f"nt:pick:{c['id']}"))
        b.row(InlineKeyboardButton(text=t(lang, "other_person"), callback_data="nt:edit:assignee"))
    row = []
    if d.get("assignee_id") and d.get("title") and d.get("due_at"):
        row.append(InlineKeyboardButton(text=t(lang, "c_send"), callback_data="nt:send"))
    row.append(InlineKeyboardButton(text=t(lang, "c_edit"), callback_data="nt:edit"))
    row.append(InlineKeyboardButton(text=t(lang, "c_cancel"), callback_data="nt:cancel"))
    b.row(*row)
    return b.as_markup()


BLOCK_ORDER = ("title", "assignee", "due", "description")


def task_block(lang: str, d: dict) -> str:
    """Vazifani oddiy matn qilib beradi — nusxa olib, xohlagan joyini tuzatib qaytariladi."""
    vals = {
        "title": d.get("title") or "—",
        "assignee": d.get("assignee_name") or "—",
        "due": fmt_due(d.get("due_at"), lang) if d.get("due_at") else "—",
        "description": " ".join((d.get("description") or "—").split()),
    }
    return "\n".join(f"{field_label(lang, k)}: {vals[k]}" for k in BLOCK_ORDER)


def edit_block_kb(lang: str, block: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if CopyTextButton is not None and len(block) <= COPY_LIMIT:
        b.row(InlineKeyboardButton(text=t(lang, "e_copy"), copy_text=CopyTextButton(text=block)))
    b.row(InlineKeyboardButton(text=t(lang, "e_buttons"), callback_data="nt:fields"),
          InlineKeyboardButton(text=t(lang, "btn_back"), callback_data="nt:back"))
    return b.as_markup()


def edit_menu_kb(lang: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text=t(lang, "e_title"), callback_data="nt:edit:title"),
          InlineKeyboardButton(text=t(lang, "e_who"), callback_data="nt:edit:assignee"))
    b.row(InlineKeyboardButton(text=t(lang, "e_due"), callback_data="nt:edit:due"),
          InlineKeyboardButton(text=t(lang, "e_desc"), callback_data="nt:edit:desc"))
    b.row(InlineKeyboardButton(text=t(lang, "btn_back"), callback_data="nt:back"))
    return b.as_markup()


def due_kb(lang: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text=t(lang, "d_today"), callback_data="nt:due:0"),
          InlineKeyboardButton(text=t(lang, "d_tomorrow"), callback_data="nt:due:1"),
          InlineKeyboardButton(text=t(lang, "d_3"), callback_data="nt:due:3"))
    b.row(InlineKeyboardButton(text=t(lang, "d_week"), callback_data="nt:due:7"),
          InlineKeyboardButton(text=t(lang, "d_custom"), callback_data="nt:due:custom"))
    return b.as_markup()


# ---------------------------------------------------------------- hisobot
def report_kb(lang: str, period: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    mark = {"week": "rep_week", "month": "rep_month", "year": "rep_year"}
    b.row(*[InlineKeyboardButton(text=("• " if p == period else "") + t(lang, k),
                                 callback_data=f"rep:{p}") for p, k in mark.items()])
    b.row(InlineKeyboardButton(text=t(lang, "rep_xlsx"), callback_data=f"rep:dl:xlsx:{period}"),
          InlineKeyboardButton(text=t(lang, "rep_csv"), callback_data=f"rep:dl:csv:{period}"))
    return b.as_markup()


def lang_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(*[InlineKeyboardButton(text=n, callback_data=f"lang:{c}")
            for c, n in (("uz", "O'zbekcha"), ("ru", "Русский"), ("en", "English"))])
    return b.as_markup()


# ---------------------------------------------------------------- xabarlar (outbox)
def notif_text(lang: str, event: str, p: dict) -> str:
    """Backend navbatga qo'ygan xabarni o'qiladigan matnga aylantiradi."""
    dep = f" · {p['department']}" if p.get("department") else ""
    due = fmt_due(p.get("due_at"), lang)
    if event == "reminder":
        head = t(lang, "n_reminder_late") if p.get("overdue") else (
            t(lang, "n_reminder_due") if str(p.get("due_at", ""))[:10] == _today() else
            t(lang, "n_reminder_soon"))
        return t(lang, "n_reminder", head=head, code=p.get("code", ""),
                 title=p.get("title", ""), due=due)
    if event == "overdue_alert":
        return t(lang, "n_overdue_alert", code=p.get("code", ""), title=p.get("title", ""),
                 assignee=p.get("assignee_name", "—"), dep=dep, due=due,
                 late=late_text(lang, p.get("late_days", 0), p.get("late_hours", 0)))
    if event == "overdue_digest":
        items = "\n".join(f"• {i['code']} {i['title'][:40]} — {i['assignee_name']} "
                          f"({t(lang, 'late_d', d=i['late_days'])})" for i in p.get("items", []))
        return t(lang, "n_overdue_digest", count=p.get("count", 0), items=items)
    if event == "due_today":
        items = "\n".join(f"• {i['code']} {i['title'][:40]} — {i['assignee_name']} "
                          f"({fmt_due(i['due_at'], lang)[-5:]})" for i in p.get("items", []))
        return t(lang, "n_due_today", count=p.get("count", 0), items=items)
    if event == "task_submitted":
        return t(lang, "n_task_submitted", code=p.get("code", ""), title=p.get("title", ""),
                 assignee=p.get("assignee_name", "—"), dep=dep, due=due,
                 ontime=t(lang, "on_time_yes" if p.get("on_time") else "on_time_no"),
                 proofs=p.get("proof_count", 0), note=p.get("note", ""))
    if event == "due_changed":
        return t(lang, "n_due_changed", code=p.get("code", ""), title=p.get("title", ""),
                 old=fmt_due(p.get("old_due"), lang), due=due)
    simple = {
        "task_created": dict(code=p.get("code", ""), title=p.get("title", ""), due=due,
                             actor=p.get("actor_name", "")),
        "task_started": dict(code=p.get("code", ""), title=p.get("title", ""),
                             actor=p.get("actor_name", "")),
        "task_accepted": dict(code=p.get("code", ""), title=p.get("title", ""),
                              actor=p.get("actor_name", "")),
        "task_returned": dict(code=p.get("code", ""), title=p.get("title", ""),
                              reason=p.get("reason", "")),
        "task_cancelled": dict(code=p.get("code", ""), title=p.get("title", ""),
                               reason=p.get("reason", "")),
        "task_unassigned": dict(code=p.get("code", ""), title=p.get("title", "")),
        "comment": dict(code=p.get("code", ""), title=p.get("title", ""),
                        actor=p.get("actor_name", ""), text=p.get("text", "")),
    }
    if event in simple:
        return t(lang, f"n_{event}", **simple[event])
    return f"{p.get('code', '')} {p.get('title', '')}".strip() or "—"


def _today() -> str:
    from datetime import date
    return date.today().isoformat()


def notif_kb(lang: str, event: str, p: dict) -> InlineKeyboardMarkup | None:
    """Xabarning o'zidan bir bosishda ish qilish — ro'yxatni ochish shart emas."""
    tid = p.get("id")
    if not tid:
        return None
    b = InlineKeyboardBuilder()
    if event == "task_submitted":
        b.row(InlineKeyboardButton(text=t(lang, "a_accept"), callback_data=f"t:acc:{tid}"),
              InlineKeyboardButton(text=t(lang, "a_return"), callback_data=f"t:ret:{tid}"))
        return b.as_markup()
    if event in ("task_created", "reminder", "task_returned"):
        b.row(InlineKeyboardButton(text=t(lang, "a_submit"), callback_data=f"t:sub:{tid}"),
              InlineKeyboardButton(text=t(lang, "a_comment"), callback_data=f"t:cm:{tid}"))
        return b.as_markup()
    if event == "overdue_alert":
        b.row(InlineKeyboardButton(text=t(lang, "a_open"), callback_data=f"t:open:{tid}"))
        return b.as_markup()
    return None


def people_text(lang: str, rows: list[dict]) -> str:
    out = [t(lang, "people_head"), ""]
    for u in rows:
        dep = f" · {u['department_name']}" if u.get("department_name") else ""
        late = f" · ⏰ {u['late_tasks']}" if u.get("late_tasks") else ""
        out.append("• " + t(lang, "people_row", name=u["full_name"], role=role_label(lang, u["role"]),
                            dep=dep, open=u.get("open_tasks", 0), late=late))
    return "\n".join(out)
