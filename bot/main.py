from __future__ import annotations

import asyncio
import logging
import re
from datetime import date, timedelta, datetime
from typing import Any, Optional

from aiogram import Bot, Dispatcher, F, Router, BaseMiddleware
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, TelegramObject, ReplyKeyboardRemove, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest

from api import api, ApiError
from config import settings
from i18n import t, block_label, prio_label, T
from render import (task_card, task_kb, tasks_list_kb, checklist_kb, main_menu, cancel_kb, confirm_card, confirm_kb,
                    edit_menu_kb, deadline_kb, prio_kb, list_kb, block_reasons_kb, lang_kb, fmt_date, loc_str)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("bot")

router = Router()


# ============ user resolution middleware ============
class UserMiddleware(BaseMiddleware):
    """Attaches data['u'] (API user dict or None) and data['lang']."""
    cache: dict[int, tuple[float, Any]] = {}

    async def __call__(self, handler, event: TelegramObject, data: dict):
        tg_user = data.get("event_from_user")
        u = None
        if tg_user:
            now = asyncio.get_event_loop().time()
            hit = self.cache.get(tg_user.id)
            if hit and hit[0] > now:
                u = hit[1]
            else:
                try:
                    u = await api.user_by_tg(tg_user.id)
                except ApiError as e:
                    log.warning("user lookup failed: %s", e)
                    u = hit[1] if hit else None
                self.cache[tg_user.id] = (now + 30, u)
        data["u"] = u
        lang = (u or {}).get("lang") or ((tg_user.language_code or "uz")[:2] if tg_user else "uz")
        data["lang"] = lang if lang in T else "uz"
        return await handler(event, data)

    @classmethod
    def invalidate(cls, tg_id: int):
        cls.cache.pop(tg_id, None)


def perms_of(u: dict | None) -> set[str]:
    return set(((u or {}).get("role") or {}).get("permissions_json") or [])


def role_of(u: dict | None) -> str:
    return ((u or {}).get("role") or {}).get("code") or ""


def is_cancel(msg: Message, lang: str) -> bool:
    txt = (msg.text or "").strip()
    return txt in {T[l]["btn_cancel"] for l in T} or txt in ("/cancel", "/bekor")


async def err(msg_or_cb, lang: str, e: ApiError):
    text = t(lang, "error", msg=e.message or e.code)
    if e.code == "REQUIRED_CHECKLIST":
        text += "\n• " + "\n• ".join(e.data.get("items", []))
    elif e.code == "REQUIRED_EVIDENCE":
        text += "\n📷 " + ", ".join(e.data.get("kinds", []))
    elif e.code == "DEPENDENCY_NOT_DONE":
        text += "\n⇢ " + ", ".join(e.data.get("codes", []))
    if isinstance(msg_or_cb, CallbackQuery):
        await msg_or_cb.answer(text[:190], show_alert=True)
    else:
        await msg_or_cb.answer(text)


async def show_task(target, lang: str, u: dict, tid: int, edit: bool = False):
    tk = await api.task(u["id"], tid)
    text, kb = task_card(lang, tk), task_kb(lang, tk)
    if isinstance(target, CallbackQuery):
        if edit:
            try:
                await target.message.edit_text(text, reply_markup=kb)
                return tk
            except TelegramBadRequest:
                pass
        await target.message.answer(text, reply_markup=kb)
    else:
        await target.answer(text, reply_markup=kb)
    return tk


# ============ states ============
class Link(StatesGroup):
    code = State()


class Report(StatesGroup):
    task = State()
    qty = State()
    workers = State()
    photos = State()


class Block(StatesGroup):
    task = State()
    note = State()


class Ret(StatesGroup):
    reason = State()


class Cmt(StatesGroup):
    text = State()


class Search(StatesGroup):
    q = State()


class NewTask(StatesGroup):
    project = State()
    assignee = State()
    reviewer = State()
    assignee_search = State()
    title = State()
    deadline = State()
    deadline_custom = State()
    prio = State()
    confirm = State()
    edit_title = State()
    edit_desc = State()
    edit_loc = State()
    edit_type = State()


# ============ start / link ============
@router.message(CommandStart())
async def start(msg: Message, state: FSMContext, u: dict | None, lang: str, command: CommandObject = None):
    await state.clear()
    if u:
        await msg.answer(t(lang, "menu"), reply_markup=main_menu(lang, perms_of(u), role_of(u)))
        return
    await msg.answer(t(lang, "welcome_unlinked"), reply_markup=ReplyKeyboardRemove())
    await state.set_state(Link.code)


@router.message(Link.code, F.text.regexp(r"^\s*\d{6}\s*$"))
async def link_code(msg: Message, state: FSMContext, lang: str):
    try:
        user = await api.consume_code(msg.text.strip(), msg.from_user.id)
    except ApiError as e:
        await msg.answer(t(lang, "code_invalid") if e.code == "CODE_INVALID" else t(lang, "error", msg=e.message))
        return
    UserMiddleware.invalidate(msg.from_user.id)
    lang = user.get("lang") or lang
    await state.clear()
    await msg.answer(t(lang, "linked", name=user["full_name"], role=user["role"]["name"]),
                     reply_markup=main_menu(lang, perms_of(user), role_of(user)))


@router.message(Link.code)
async def link_other(msg: Message, lang: str):
    await msg.answer(t(lang, "ask_code"))


# ============ language / help ============
@router.message(Command("til", "lang", "language"))
@router.message(F.text.in_({T[l]["btn_lang"] for l in T}))
async def lang_cmd(msg: Message, lang: str):
    await msg.answer(t(lang, "lang_pick"), reply_markup=lang_kb())


@router.callback_query(F.data.startswith("lang:"))
async def lang_set(cb: CallbackQuery, u: dict | None):
    new = cb.data.split(":")[1]
    if u:
        try:
            await api.set_lang(u["id"], new)
        except ApiError:
            pass
        UserMiddleware.invalidate(cb.from_user.id)
        u = dict(u, lang=new)
    await cb.message.edit_text(t(new, "lang_set"))
    await cb.message.answer(t(new, "menu"), reply_markup=main_menu(new, perms_of(u), role_of(u)))


@router.message(Command("help", "yordam"))
@router.message(F.text.in_({T[l]["btn_help"] for l in T}))
async def help_cmd(msg: Message, lang: str):
    await msg.answer(t(lang, "help"))


# ============ cancel (any state) ============
@router.message(F.text.in_({T[l]["btn_cancel"] for l in T}))
@router.message(Command("cancel", "bekor"))
async def cancel_any(msg: Message, state: FSMContext, u: dict | None, lang: str):
    await state.clear()
    await msg.answer(t(lang, "cancelled"), reply_markup=main_menu(lang, perms_of(u), role_of(u)) if u else ReplyKeyboardRemove())


# ============ my tasks / review queue ============
@router.message(Command("vazifalarim", "tasks", "my"))
@router.message(F.text.in_({T[l]["btn_my"] for l in T}))
async def my_tasks(msg: Message, u: dict | None, lang: str):
    if not u:
        return await msg.answer(t(lang, "not_linked"))
    try:
        page = await api.tasks(u["id"], mine=True, status="plan,progress,blocked,review", sort="planned_end", limit=50)
    except ApiError as e:
        return await err(msg, lang, e)
    today = date.today().isoformat()
    items = [x for x in page["items"] if x["planned_end"] <= today or x["status"] in ("blocked", "progress")]
    items = items or page["items"]
    if not items:
        return await msg.answer(t(lang, "no_tasks"))
    await msg.answer(t(lang, "my_tasks_title", n=len(items)), reply_markup=tasks_list_kb(lang, items))


@router.message(Command("tekshiruv", "review"))
@router.message(F.text.in_({T[l]["btn_review"] for l in T}))
async def review_queue(msg: Message, u: dict | None, lang: str):
    if not u:
        return await msg.answer(t(lang, "not_linked"))
    try:
        page = await api.tasks(u["id"], review_queue=True, sort="updated_at", limit=50)
    except ApiError as e:
        return await err(msg, lang, e)
    if not page["items"]:
        return await msg.answer(t(lang, "review_empty"))
    await msg.answer(t(lang, "review_title", n=page["total"]), reply_markup=tasks_list_kb(lang, page["items"]))


# ============ search ============
@router.message(Command("qidir", "find"))
async def search_cmd(msg: Message, state: FSMContext, u: dict | None, lang: str, command: CommandObject):
    if not u:
        return await msg.answer(t(lang, "not_linked"))
    if command.args:
        return await do_search(msg, u, lang, command.args)
    await state.set_state(Search.q)
    await msg.answer(t(lang, "search_ask"), reply_markup=cancel_kb(lang))


@router.message(F.text.in_({T[l]["btn_search"] for l in T}))
async def search_btn(msg: Message, state: FSMContext, u: dict | None, lang: str):
    if not u:
        return await msg.answer(t(lang, "not_linked"))
    await state.set_state(Search.q)
    await msg.answer(t(lang, "search_ask"), reply_markup=cancel_kb(lang))


@router.message(Search.q)
async def search_q(msg: Message, state: FSMContext, u: dict, lang: str):
    await state.clear()
    await msg.answer("…", reply_markup=main_menu(lang, perms_of(u), role_of(u)))
    await do_search(msg, u, lang, msg.text or "")


async def do_search(msg: Message, u: dict, lang: str, q: str):
    q = q.strip()
    m = re.match(r"^v?-?\s*(\d+)$", q, re.I)
    try:
        if m:
            tk = await api.task_by_code(u["id"], f"V-{m.group(1)}")
            return await msg.answer(task_card(lang, tk), reply_markup=task_kb(lang, tk))
        page = await api.tasks(u["id"], q=q, limit=20)
        if not page["items"]:
            return await msg.answer(t(lang, "search_none"))
        await msg.answer(f"🔎 {page['total']}", reply_markup=tasks_list_kb(lang, page["items"]))
    except ApiError as e:
        if e.status == 404:
            return await msg.answer(t(lang, "search_none"))
        await err(msg, lang, e)


# ============ manager sections: reports / overdue / blocked / team ============
def _needs(u: dict | None, perm: str) -> bool:
    return bool(u) and perm in perms_of(u)


async def _task_list(msg: Message, u: dict, lang: str, title_key: str, **filters):
    try:
        page = await api.tasks(u["id"], sort="planned_end", limit=30, **filters)
    except ApiError as e:
        return await err(msg, lang, e)
    items = page["items"]
    if not items:
        return await msg.answer(t(lang, "list_empty_ok"))
    await msg.answer(t(lang, title_key, n=page["total"]), reply_markup=tasks_list_kb(lang, items))


@router.message(Command("kechikkan", "overdue"))
@router.message(F.text.in_({T[l]["btn_overdue"] for l in T}))
async def overdue_list(msg: Message, u: dict | None, lang: str):
    if not u:
        return await msg.answer(t(lang, "not_linked"))
    if not _needs(u, "reports.read"):
        return await msg.answer(t(lang, "no_perm"))
    await _task_list(msg, u, lang, "list_overdue", overdue=True)


@router.message(Command("bloklangan", "blocked"))
@router.message(F.text.in_({T[l]["btn_blocked"] for l in T}))
async def blocked_list(msg: Message, u: dict | None, lang: str):
    if not u:
        return await msg.answer(t(lang, "not_linked"))
    if not _needs(u, "reports.read"):
        return await msg.answer(t(lang, "no_perm"))
    await _task_list(msg, u, lang, "list_blocked", blocked=True)


@router.message(Command("umumiy", "summary", "kpi"))
@router.message(F.text.in_({T[l]["btn_reports"] for l in T}))
async def summary_report(msg: Message, u: dict | None, lang: str):
    if not u:
        return await msg.answer(t(lang, "not_linked"))
    if not _needs(u, "reports.read"):
        return await msg.answer(t(lang, "no_perm"))
    try:
        s = await api.summary(u["id"])
    except ApiError as e:
        return await err(msg, lang, e)
    k = s["kpi"]
    if not k["total"]:
        return await msg.answer(t(lang, "rep_empty"))
    scope = f" — {u['role']['name']}"
    out = t(lang, "rep_title", scope=scope) + "\n\n" + t(
        lang, "rep_line", open=k["open"], overdue=k["overdue"], blocked=k["blocked"], review=k["review"],
        oldest=k["review_oldest_days"], ontime=f"{k['on_time_pct']}%" if k["on_time_pct"] is not None else "—",
        ret=f"{k['return_pct']}%")
    reasons = [r for r in s.get("blocked_reasons", []) if r.get("count")]
    if reasons:
        out += t(lang, "rep_reasons")
        for r in reasons[:5]:
            out += f"\n• {block_label(lang, r['code'])}: <b>{r['count']}</b>"
    staff = [x for x in s.get("staff", []) if x["open"] or x["overdue"]][:8]
    if staff:
        out += t(lang, "rep_staff")
        for x in staff:
            late = f" · ⏱ <b>{x['overdue']}</b>" if x["overdue"] else ""
            out += f"\n• {x['name']}: {x['open']}{late}"
    await msg.answer(out)


@router.message(Command("jamoa", "team"))
@router.message(F.text.in_({T[l]["btn_team"] for l in T}))
async def team_list(msg: Message, u: dict | None, lang: str):
    if not u:
        return await msg.answer(t(lang, "not_linked"))
    if not _needs(u, "admin.users"):
        return await msg.answer(t(lang, "no_perm"))
    try:
        users = await api.users(u["id"])
    except ApiError as e:
        return await err(msg, lang, e)
    lines = [t(lang, "team_title", n=len(users))]
    for x in users:
        lines.append(t(lang, "team_line", icon="🟢" if x.get("is_active", True) else "⚪",
                       name=x["full_name"], role=(x.get("role") or {}).get("name", ""),
                       tg=" ✈" if x.get("telegram_user_id") else ""))
    await msg.answer("\n".join(lines[:60]))


# ============ task actions (inline) ============
@router.callback_query(F.data.startswith("t:"))
async def task_action(cb: CallbackQuery, state: FSMContext, u: dict | None, lang: str):
    if not u:
        return await cb.answer(t(lang, "not_linked"), show_alert=True)
    _, action, tid = cb.data.split(":")
    tid = int(tid)
    uid = u["id"]
    try:
        if action == "show":
            await show_task(cb, lang, u, tid, edit=True)
            await cb.answer()
        elif action == "start":
            await api.start(uid, tid)
            await cb.answer(t(lang, "started"))
            await show_task(cb, lang, u, tid, edit=True)
        elif action == "review":
            await api.submit_review(uid, tid)
            await cb.answer(t(lang, "sent_review"))
            await show_task(cb, lang, u, tid, edit=True)
        elif action == "accept":
            await api.accept(uid, tid)
            await cb.answer(t(lang, "accepted"))
            await show_task(cb, lang, u, tid, edit=True)
        elif action == "unblock":
            await api.unblock(uid, tid)
            await cb.answer(t(lang, "unblocked"))
            await show_task(cb, lang, u, tid, edit=True)
        elif action == "return":
            await state.set_state(Ret.reason)
            await state.update_data(tid=tid)
            await cb.message.answer(t(lang, "ask_return_reason"), reply_markup=cancel_kb(lang))
            await cb.answer()
        elif action == "comment":
            await state.set_state(Cmt.text)
            await state.update_data(tid=tid)
            await cb.message.answer(t(lang, "ask_comment"), reply_markup=cancel_kb(lang))
            await cb.answer()
        elif action == "ck":
            tk = await api.task(uid, tid)
            await cb.message.edit_text(t(lang, "checklist_title") + f"\n<b>{tk['code']}</b> {tk['title']}", reply_markup=checklist_kb(lang, tk))
            await cb.answer()
        elif action == "report":
            await start_report(cb.message, state, u, lang, tid)
            await cb.answer()
        elif action == "block":
            await state.set_state(Block.task)
            await state.update_data(tid=tid)
            await cb.message.answer(t(lang, "problem_reason"), reply_markup=block_reasons_kb(lang, tid))
            await cb.answer()
        else:
            await cb.answer()
    except ApiError as e:
        await err(cb, lang, e)


@router.callback_query(F.data.startswith("ck:"))
async def checklist_toggle(cb: CallbackQuery, u: dict | None, lang: str):
    if not u:
        return await cb.answer(t(lang, "not_linked"), show_alert=True)
    _, tid, iid, val = cb.data.split(":")
    try:
        tk = await api.checklist_set(u["id"], int(tid), [{"id": int(iid), "is_done": val == "1"}])
        await cb.message.edit_reply_markup(reply_markup=checklist_kb(lang, tk))
        await cb.answer(f"{tk['checklist_done']}/{tk['checklist_total']}")
    except ApiError as e:
        await err(cb, lang, e)


@router.message(Ret.reason)
async def ret_reason(msg: Message, state: FSMContext, u: dict, lang: str):
    d = await state.get_data()
    await state.clear()
    try:
        await api.return_task(u["id"], d["tid"], msg.text or "")
        await msg.answer(t(lang, "returned"), reply_markup=main_menu(lang, perms_of(u), role_of(u)))
        await show_task(msg, lang, u, d["tid"])
    except ApiError as e:
        await err(msg, lang, e)


@router.message(Cmt.text)
async def cmt_text(msg: Message, state: FSMContext, u: dict, lang: str):
    d = await state.get_data()
    await state.clear()
    try:
        await api.comment(u["id"], d["tid"], msg.text or msg.caption or "")
        await msg.answer(t(lang, "commented"), reply_markup=main_menu(lang, perms_of(u), role_of(u)))
    except ApiError as e:
        await err(msg, lang, e)


# ============ daily report ============
@router.message(Command("hisobot", "report"))
@router.message(F.text.in_({T[l]["btn_report"] for l in T}))
async def report_cmd(msg: Message, state: FSMContext, u: dict | None, lang: str):
    if not u:
        return await msg.answer(t(lang, "not_linked"))
    try:
        page = await api.tasks(u["id"], mine=True, status="progress,blocked", sort="planned_end", limit=20)
    except ApiError as e:
        return await err(msg, lang, e)
    items = page["items"]
    if not items:
        return await msg.answer(t(lang, "no_tasks"))
    if len(items) == 1:
        return await start_report(msg, state, u, lang, items[0]["id"])
    await state.set_state(Report.task)
    picks = [{"id": x["id"], "name": f"{x['code']} · {x['title']}"} for x in items]
    await state.update_data(_rep_items=picks)
    await msg.answer(t(lang, "pick_task"), reply_markup=list_kb(picks, "rep"))


@router.callback_query(F.data.startswith("rep_pg:"))
async def rep_page(cb: CallbackQuery, state: FSMContext, lang: str):
    d = await state.get_data()
    await cb.message.edit_reply_markup(reply_markup=list_kb(d.get("_rep_items", []), "rep", page=int(cb.data.split(":")[1])))
    await cb.answer()


@router.callback_query(F.data.startswith("rep:"))
async def report_pick(cb: CallbackQuery, state: FSMContext, u: dict | None, lang: str):
    if not u:
        return await cb.answer()
    await cb.answer()
    await start_report(cb.message, state, u, lang, int(cb.data.split(":")[1]))


async def start_report(msg: Message, state: FSMContext, u: dict, lang: str, tid: int):
    try:
        tk = await api.task(u["id"], tid)
    except ApiError as e:
        return await err(msg, lang, e)
    await state.set_state(Report.qty)
    await state.update_data(tid=tid, unit=tk.get("unit") or "", plan=tk.get("planned_quantity"), photos=0, daily_id=None, code=tk["code"])
    await msg.answer(f"<b>{tk['code']}</b> {tk['title']}\n" + t(lang, "report_qty", unit=tk.get("unit") or "—", plan=tk.get("planned_quantity") or "—"),
                     reply_markup=cancel_kb(lang, skip=True))


def _num(s: str) -> Optional[float]:
    s = (s or "").replace(",", ".").strip()
    m = re.search(r"-?\d+(\.\d+)?", s)
    return float(m.group(0)) if m else None


@router.message(Report.qty)
async def report_qty(msg: Message, state: FSMContext, lang: str):
    skip = (msg.text or "") in {T[l]["btn_skip"] for l in T}
    qty = None if skip else _num(msg.text or "")
    if not skip and qty is None:
        return await msg.answer(t(lang, "report_qty", unit=(await state.get_data()).get("unit") or "—", plan=(await state.get_data()).get("plan") or "—"))
    await state.update_data(qty=qty)
    await state.set_state(Report.workers)
    await msg.answer(t(lang, "report_workers"), reply_markup=cancel_kb(lang, skip=True))


@router.message(Report.workers)
async def report_workers(msg: Message, state: FSMContext, u: dict, lang: str):
    skip = (msg.text or "") in {T[l]["btn_skip"] for l in T}
    w = None if skip else _num(msg.text or "")
    d = await state.get_data()
    try:
        row = await api.daily(u["id"], d["tid"], {"date": date.today().isoformat(), "quantity": d.get("qty"),
                                                  "workers_count": int(w) if w is not None else None})
    except ApiError as e:
        await state.clear()
        return await err(msg, lang, e)
    await state.update_data(daily_id=row["id"], workers=w, dup=row.get("is_duplicate"))
    await state.set_state(Report.photos)
    await msg.answer(t(lang, "report_photo"), reply_markup=cancel_kb(lang, done=True))


@router.message(Report.photos, F.photo | F.document)
async def report_photo(msg: Message, state: FSMContext, u: dict, lang: str, bot: Bot):
    d = await state.get_data()
    if msg.photo:
        f = msg.photo[-1]
        filename, mime = f"photo_{f.file_unique_id}.jpg", "image/jpeg"
    else:
        f = msg.document
        filename, mime = f.file_name or "file", f.mime_type or "application/octet-stream"
    buf = await bot.download(f)
    data = buf.read()
    kind = "during" if mime.startswith("image/") else "document"
    try:
        await api.upload(u["id"], d["tid"], data, filename, mime, kind, d.get("daily_id"))
    except ApiError as e:
        return await err(msg, lang, e)
    n = (d.get("photos") or 0) + 1
    await state.update_data(photos=n)
    await msg.answer(t(lang, "photo_saved", n=n))


@router.message(Report.photos)
async def report_done(msg: Message, state: FSMContext, u: dict, lang: str):
    d = await state.get_data()
    await state.clear()
    try:
        tk = await api.task(u["id"], d["tid"])
    except ApiError as e:
        return await err(msg, lang, e)
    plan = tk.get("planned_quantity")
    pct = round(float(tk.get("actual_quantity") or 0) / float(plan) * 100) if plan else tk.get("progress_percent", 0)
    txt = t(lang, "report_saved", date=date.today().strftime("%d.%m"), qty=d.get("qty") if d.get("qty") is not None else "—",
            unit=d.get("unit") or "", workers=int(d["workers"]) if d.get("workers") is not None else "—", photos=d.get("photos", 0),
            total=tk.get("actual_quantity") or 0, plan=plan or "—", pct=pct)
    if d.get("dup"):
        txt += "\n" + t(lang, "report_dup")
    await msg.answer(txt, reply_markup=main_menu(lang, perms_of(u), role_of(u)))


# ============ block (/muammo) ============
@router.message(Command("muammo", "problem"))
@router.message(F.text.in_({T[l]["btn_problem"] for l in T}))
async def problem_cmd(msg: Message, state: FSMContext, u: dict | None, lang: str):
    if not u:
        return await msg.answer(t(lang, "not_linked"))
    try:
        page = await api.tasks(u["id"], mine=True, status="plan,progress,review", sort="planned_end", limit=20)
    except ApiError as e:
        return await err(msg, lang, e)
    items = page["items"]
    if not items:
        return await msg.answer(t(lang, "no_tasks"))
    await state.set_state(Block.task)
    picks = [{"id": x["id"], "name": f"{x['code']} · {x['title']}"} for x in items]
    await state.update_data(_blk_items=picks)
    await msg.answer(t(lang, "pick_task"), reply_markup=list_kb(picks, "blkt"))


@router.callback_query(F.data.startswith("blkt_pg:"))
async def blkt_page(cb: CallbackQuery, state: FSMContext, lang: str):
    d = await state.get_data()
    await cb.message.edit_reply_markup(reply_markup=list_kb(d.get("_blk_items", []), "blkt", page=int(cb.data.split(":")[1])))
    await cb.answer()


@router.callback_query(F.data.startswith("blkt:"))
async def block_pick(cb: CallbackQuery, state: FSMContext, lang: str):
    tid = int(cb.data.split(":")[1])
    await state.update_data(tid=tid)
    await cb.message.edit_text(t(lang, "problem_reason"), reply_markup=block_reasons_kb(lang, tid))
    await cb.answer()


@router.callback_query(F.data.startswith("blk:"))
async def block_reason(cb: CallbackQuery, state: FSMContext, lang: str):
    _, tid, reason = cb.data.split(":")
    await state.set_state(Block.note)
    await state.update_data(tid=int(tid), reason=reason)
    await cb.message.edit_text(f"⛔ {block_label(lang, reason)}")
    await cb.message.answer(t(lang, "problem_note"), reply_markup=cancel_kb(lang))
    await cb.answer()


@router.message(Block.note)
async def block_note(msg: Message, state: FSMContext, u: dict, lang: str):
    d = await state.get_data()
    await state.clear()
    try:
        await api.block(u["id"], d["tid"], d["reason"], msg.text or "")
        await msg.answer(t(lang, "problem_saved"), reply_markup=main_menu(lang, perms_of(u), role_of(u)))
        await show_task(msg, lang, u, d["tid"])
    except ApiError as e:
        await err(msg, lang, e)


# ============ NEW TASK: wizard + voice ============
def _can_create(u: dict | None) -> bool:
    return bool(u) and "tasks.create" in perms_of(u)


def _has(x: dict, perm: str) -> bool:
    return perm in ((x.get("role") or {}).get("permissions_json") or [])


def _can_accept(x: dict) -> bool:
    """Vazifani qabul qila oladimi - tekshiruvchi qilib tayinlash mumkinmi."""
    return _has(x, "tasks.accept")


def _can_do(x: dict) -> bool:
    """Ishni bajara oladimi - bajaruvchi qilib tayinlash mumkinmi."""
    return _has(x, "tasks.start")


async def default_reviewer(uid: int, project_id: int | None, creator_id: int) -> dict | None:
    """Kim tekshiradi: loyihaning tekshiruvchisi -> rahbari -> (topilmasa) "tasks.accept" huquqi bor
    boshqa odam (masalan superadmin). Bu huquqi yo'q odam (masalan prorab) hech qachon tanlanmaydi -
    aks holda vazifa hech kim qabul qila olmaydigan holatda tekshiruvda abadiy osilib qoladi."""
    if not project_id:
        return None
    try:
        users = [x for x in await api.users(uid, project_id=project_id) if x["id"] != creator_id and _can_accept(x)]
    except ApiError:
        return None
    order = {"tekshiruvchi": 0, "rahbar": 1}
    users.sort(key=lambda x: order.get((x.get("role") or {}).get("code", ""), 2))
    return users[0] if users else None


async def _apply_default_reviewer(state: FSMContext, u: dict):
    d = await state.get_data()
    if d.get("reviewer_id") and d.get("reviewer_id") != u["id"]:
        return
    rev = await default_reviewer(u["id"], d.get("project_id"), d.get("assignee_id") or 0)
    if rev and rev["id"] != d.get("assignee_id"):
        await state.update_data(reviewer_id=rev["id"], reviewer_name=rev["full_name"])
    else:
        await state.update_data(reviewer_id=u["id"], reviewer_name=u["full_name"])


async def _names(uid: int, d: dict) -> dict:
    """Resolve ids -> display names for the confirm card."""
    names = {}
    try:
        if d.get("project_id"):
            names["project"] = d.get("project_name") or next((p["name"] for p in await api.projects(uid) if p["id"] == d["project_id"]), None)
        if d.get("assignee_id"):
            names["assignee"] = d.get("assignee_name")
            if not names["assignee"]:
                users = await api.users(uid)
                names["assignee"] = next((x["full_name"] for x in users if x["id"] == d["assignee_id"]), None)
        if d.get("reviewer_id"):
            names["reviewer"] = d.get("reviewer_name")
            if not names["reviewer"]:
                users = await api.users(uid)
                names["reviewer"] = next((x["full_name"] for x in users if x["id"] == d["reviewer_id"]), None)
        names["location"] = d.get("location_name")
        names["type"] = d.get("type_name")
    except ApiError:
        pass
    return names


async def show_confirm(target, state: FSMContext, uid: int, lang: str, edit=False):
    d = await state.get_data()
    names = await _names(uid, d)
    text, kb = confirm_card(lang, d, names), confirm_kb(lang, d)
    await state.set_state(NewTask.confirm)
    if isinstance(target, CallbackQuery) and edit:
        try:
            await target.message.edit_text(text, reply_markup=kb)
            return
        except TelegramBadRequest:
            pass
    m = target.message if isinstance(target, CallbackQuery) else target
    await m.answer(text, reply_markup=kb)


async def _default_type(uid: int, d: dict):
    if d.get("type_id"):
        return
    types = await api.task_types(uid)
    if types:
        gen = next((x for x in types if (x.get("group_name") or "").lower() in ("umumiy", "general", "общие")), types[0])
        d["type_id"], d["type_name"] = gen["id"], gen["name"]


@router.message(Command("yangi", "new"))
@router.message(F.text.in_({T[l]["btn_new"] for l in T}))
async def new_task(msg: Message, state: FSMContext, u: dict | None, lang: str):
    if not u:
        return await msg.answer(t(lang, "not_linked"))
    if not _can_create(u):
        return await msg.answer(t(lang, "no_perm"))
    await state.clear()
    await state.set_data({"transcript": None, "priority": "normal", "planned_start": date.today().isoformat(), "warnings": []})
    await ask_project(msg, state, u, lang)


async def ask_project(msg: Message, state: FSMContext, u: dict, lang: str, edit_cb: CallbackQuery | None = None):
    projects = await api.projects(u["id"])
    if len(projects) == 1 and not edit_cb:
        await state.update_data(project_id=projects[0]["id"], project_name=projects[0]["name"])
        return await ask_assignee(msg, state, u, lang)
    await state.set_state(NewTask.project)
    picks = [{"id": p["id"], "name": p["name"]} for p in projects]
    await state.update_data(_projects=picks)
    kb = list_kb(picks, "ntp")
    if edit_cb:
        await edit_cb.message.edit_text(t(lang, "nt_project"), reply_markup=kb)
    else:
        await msg.answer(t(lang, "nt_project"), reply_markup=kb)


@router.callback_query(F.data.startswith("ntp_pg:"))
async def ntp_page(cb: CallbackQuery, state: FSMContext, lang: str):
    d = await state.get_data()
    await cb.message.edit_reply_markup(reply_markup=list_kb(d.get("_projects", []), "ntp", page=int(cb.data.split(":")[1])))
    await cb.answer()


@router.callback_query(F.data.startswith("ntp:"))
async def nt_project(cb: CallbackQuery, state: FSMContext, u: dict, lang: str):
    pid = int(cb.data.split(":")[1])
    projects = await api.projects(u["id"])
    p = next((x for x in projects if x["id"] == pid), None)
    await state.update_data(project_id=pid, project_name=p["name"] if p else None, location_id=None, location_name=None,
                            reviewer_id=None, reviewer_name=None)
    await _apply_default_reviewer(state, u)
    await cb.answer()
    d = await state.get_data()
    if d.get("_editing") or d.get("title"):
        await state.update_data(_editing=False)
        return await show_confirm(cb, state, u["id"], lang, edit=True)
    await ask_assignee(cb.message, state, u, lang, edit_msg=True)


async def ask_assignee(msg: Message, state: FSMContext, u: dict, lang: str, edit_msg=False, page=0):
    d = await state.get_data()
    # faqat ishni bajara oladigan odam (tasks.start) - tekshiruvchi/kuzatuvchiga vazifa berilsa
    # u uni boshlay olmaydi va vazifa "rejada" holatida qotib qoladi
    users = [x for x in await api.users(u["id"], project_id=d.get("project_id")) if _can_do(x)]
    users = [x for x in users if x["id"] != u["id"]] or users
    await state.update_data(_users=[{"id": x["id"], "name": x["full_name"]} for x in users])
    await state.set_state(NewTask.assignee)
    kb = list_kb([{"id": x["id"], "name": x["full_name"]} for x in users], "nta", page=page)
    if edit_msg:
        try:
            return await msg.edit_text(t(lang, "nt_assignee"), reply_markup=kb)
        except TelegramBadRequest:
            pass
    await msg.answer(t(lang, "nt_assignee"), reply_markup=kb)


@router.callback_query(F.data.startswith("nta_pg:"))
async def nta_page(cb: CallbackQuery, state: FSMContext, lang: str):
    d = await state.get_data()
    await cb.message.edit_reply_markup(reply_markup=list_kb(d.get("_users", []), "nta", page=int(cb.data.split(":")[1])))
    await cb.answer()


@router.message(NewTask.assignee, F.text)
async def nta_search(msg: Message, state: FSMContext, u: dict, lang: str):
    """Typing a name filters the list."""
    d = await state.get_data()
    q = (msg.text or "").lower().strip()
    users = [x for x in d.get("_users", []) if q in x["name"].lower()]
    if not users:
        # fall back to fuzzy via API parse (rapidfuzz on server)
        try:
            parsed = await api.parse_task(u["id"], f"{msg.text} uchun", lang, d.get("project_id"))
            users = [{"id": c["id"], "name": f"{c['full_name']} ({c['score']}%)"} for c in parsed.get("assignee_candidates", [])]
        except ApiError:
            users = []
    if not users:
        return await msg.answer(t(lang, "search_none"))
    await msg.answer(t(lang, "nt_assignee"), reply_markup=list_kb(users, "nta"))


@router.callback_query(F.data.startswith("nta:"))
async def nt_assignee(cb: CallbackQuery, state: FSMContext, u: dict, lang: str):
    aid = int(cb.data.split(":")[1])
    d = await state.get_data()
    name = next((x["name"].split(" (")[0] for x in d.get("_users", []) if x["id"] == aid), None)
    if not name:
        users = await api.users(u["id"])
        name = next((x["full_name"] for x in users if x["id"] == aid), "?")
    await state.update_data(assignee_id=aid, assignee_name=name, assignee_candidates=[])
    await _apply_default_reviewer(state, u)
    await cb.answer()
    if d.get("title"):
        return await show_confirm(cb, state, u["id"], lang, edit=True)
    await state.set_state(NewTask.title)
    await cb.message.edit_text(f"👤 {name}")
    await cb.message.answer(t(lang, "nt_title"), reply_markup=cancel_kb(lang))


@router.callback_query(F.data.startswith("nt:pick_a:"))
async def nt_pick_candidate(cb: CallbackQuery, state: FSMContext, u: dict, lang: str):
    aid = int(cb.data.split(":")[2])
    d = await state.get_data()
    c = next((c for c in d.get("assignee_candidates", []) if c["id"] == aid), None)
    await state.update_data(assignee_id=aid, assignee_name=c["full_name"] if c else None, assignee_candidates=[])
    await _apply_default_reviewer(state, u)
    await cb.answer()
    await show_confirm(cb, state, u["id"], lang, edit=True)


async def ask_reviewer(msg: Message, state: FSMContext, u: dict, lang: str, edit_msg=False):
    d = await state.get_data()
    users = await api.users(u["id"], project_id=d.get("project_id"))
    # faqat "tasks.accept" huquqi bor odam - aks holda vazifa tekshiruvda osilib qoladi
    users = [x for x in users if x["id"] != d.get("assignee_id") and _can_accept(x)]
    await state.update_data(_revs=[{"id": x["id"], "name": f"{x['full_name']} · {(x.get('role') or {}).get('name','')}"} for x in users])
    await state.set_state(NewTask.reviewer)
    kb = list_kb([{"id": x["id"], "name": x["full_name"]} for x in users], "ntr")
    if edit_msg:
        try:
            return await msg.edit_text(t(lang, "nt_reviewer"), reply_markup=kb)
        except TelegramBadRequest:
            pass
    await msg.answer(t(lang, "nt_reviewer"), reply_markup=kb)


@router.callback_query(F.data.startswith("ntr_pg:"))
async def ntr_page(cb: CallbackQuery, state: FSMContext, lang: str):
    d = await state.get_data()
    await cb.message.edit_reply_markup(reply_markup=list_kb(d.get("_revs", []), "ntr", page=int(cb.data.split(":")[1])))
    await cb.answer()


@router.callback_query(F.data.startswith("ntr:"))
async def nt_reviewer(cb: CallbackQuery, state: FSMContext, u: dict, lang: str):
    rid = int(cb.data.split(":")[1])
    d = await state.get_data()
    name = next((x["name"].split(" · ")[0] for x in d.get("_revs", []) if x["id"] == rid), None)
    if not name:
        users = await api.users(u["id"])
        name = next((x["full_name"] for x in users if x["id"] == rid), None)
    await state.update_data(reviewer_id=rid, reviewer_name=name, _editing=False)
    await cb.answer()
    await show_confirm(cb, state, u["id"], lang, edit=True)


@router.message(NewTask.title, F.text)
async def nt_title(msg: Message, state: FSMContext, u: dict, lang: str):
    await state.update_data(title=msg.text.strip()[:250])
    d = await state.get_data()
    if d.get("planned_end"):
        return await show_confirm(msg, state, u["id"], lang)
    await state.set_state(NewTask.deadline)
    await msg.answer(t(lang, "nt_deadline"), reply_markup=deadline_kb(lang))


def _eom() -> date:
    today = date.today()
    nxt = (today.replace(day=28) + timedelta(days=4)).replace(day=1)
    return nxt - timedelta(days=1)


@router.callback_query(F.data.startswith("nt:dl:"))
async def nt_deadline(cb: CallbackQuery, state: FSMContext, u: dict, lang: str):
    v = cb.data.split(":")[2]
    if v == "custom":
        await state.set_state(NewTask.deadline_custom)
        await cb.message.answer(t(lang, "nt_deadline_custom"), reply_markup=cancel_kb(lang))
        return await cb.answer()
    end = _eom() if v == "eom" else date.today() + timedelta(days=int(v))
    await _set_deadline(cb, state, u, lang, end)


async def _set_deadline(target, state: FSMContext, u: dict, lang: str, end: date):
    d = await state.get_data()
    start = date.fromisoformat(d.get("planned_start") or date.today().isoformat())
    if end < start:
        start = end
    w = [x for x in (d.get("warnings") or []) if x != "no_deadline"]
    await state.update_data(planned_end=end.isoformat(), planned_start=start.isoformat(), warnings=w)
    if isinstance(target, CallbackQuery):
        await target.answer()
    d = await state.get_data()
    if d.get("transcript") or d.get("_editing"):
        await state.update_data(_editing=False)
        return await show_confirm(target, state, u["id"], lang, edit=isinstance(target, CallbackQuery))
    await state.set_state(NewTask.prio)
    m = target.message if isinstance(target, CallbackQuery) else target
    await m.answer(t(lang, "nt_priority"), reply_markup=prio_kb(lang))


def parse_date(s: str) -> Optional[date]:
    s = s.strip()
    for fmt in ("%d.%m.%Y", "%d.%m.%y", "%d.%m", "%Y-%m-%d", "%d/%m/%Y", "%d/%m"):
        try:
            d = datetime.strptime(s, fmt).date()
            if "%Y" not in fmt and "%y" not in fmt:
                d = d.replace(year=date.today().year)
                if d < date.today() - timedelta(days=30):
                    d = d.replace(year=d.year + 1)
            return d
        except ValueError:
            continue
    return None


@router.message(NewTask.deadline_custom, F.text)
async def nt_deadline_custom(msg: Message, state: FSMContext, u: dict, lang: str):
    d = parse_date(msg.text or "")
    if not d:
        return await msg.answer(t(lang, "nt_bad_date"))
    await _set_deadline(msg, state, u, lang, d)


@router.callback_query(F.data.startswith("nt:prio:"))
async def nt_prio(cb: CallbackQuery, state: FSMContext, u: dict, lang: str):
    await state.update_data(priority=cb.data.split(":")[2], _editing=False)
    await cb.answer()
    d = await state.get_data()
    await _default_type(u["id"], d)
    await state.update_data(type_id=d.get("type_id"), type_name=d.get("type_name"))
    await show_confirm(cb, state, u["id"], lang, edit=True)


# ---- confirm / edit / send ----
@router.callback_query(F.data == "nt:send")
async def nt_send(cb: CallbackQuery, state: FSMContext, u: dict, lang: str):
    d = await state.get_data()
    body = {"project_id": d.get("project_id"), "location_id": d.get("location_id"), "type_id": d.get("type_id"),
            "title": d.get("title"), "description": d.get("description"), "priority": d.get("priority") or "normal",
            "assignee_id": d.get("assignee_id"), "reviewer_id": d.get("reviewer_id") or u["id"],
            "planned_start": d.get("planned_start") or date.today().isoformat(), "planned_end": d.get("planned_end")}
    if body["reviewer_id"] == body["assignee_id"]:
        body["reviewer_id"] = u["id"]
    try:
        tk = await api.create_task(u["id"], body)
    except ApiError as e:
        return await err(cb, lang, e)
    await state.clear()
    await cb.message.edit_text(t(lang, "created", code=tk["code"], title=tk["title"], assignee=tk["assignee_name"], end=fmt_date(tk["planned_end"])))
    await cb.message.answer(task_card(lang, tk), reply_markup=task_kb(lang, tk))
    await cb.answer()


@router.callback_query(F.data == "nt:cancel")
async def nt_cancel(cb: CallbackQuery, state: FSMContext, u: dict, lang: str):
    await state.clear()
    await cb.message.edit_text(t(lang, "cancelled"))
    await cb.answer()


@router.callback_query(F.data == "nt:back")
async def nt_back(cb: CallbackQuery, state: FSMContext, u: dict, lang: str):
    await cb.answer()
    await show_confirm(cb, state, u["id"], lang, edit=True)


@router.callback_query(F.data == "nt:edit")
async def nt_edit_menu(cb: CallbackQuery, state: FSMContext, lang: str):
    # Tugmalar qoladi, lekin asosiysi - shunchaki yozib tuzatish mumkinligini aytamiz
    await cb.message.edit_reply_markup(reply_markup=edit_menu_kb(lang))
    await cb.message.answer(t(lang, "e_free"))
    await cb.answer()


@router.callback_query(F.data.startswith("nt:edit:"))
async def nt_edit_field(cb: CallbackQuery, state: FSMContext, u: dict, lang: str):
    field = cb.data.split(":")[2]
    await state.update_data(_editing=True)
    await cb.answer()
    uid = u["id"]
    if field == "title":
        await state.set_state(NewTask.edit_title)
        d = await state.get_data()
        cur = (d.get("title") or "").strip()
        ask = t(lang, "e_title_now", cur=cur) if cur else t(lang, "e_title_ask")
        await cb.message.answer(ask, reply_markup=cancel_kb(lang))
    elif field == "desc":
        await state.set_state(NewTask.edit_desc)
        await cb.message.answer(t(lang, "e_desc_ask"), reply_markup=cancel_kb(lang))
    elif field == "assignee":
        await ask_assignee(cb.message, state, u, lang, edit_msg=True)
    elif field == "reviewer":
        await ask_reviewer(cb.message, state, u, lang, edit_msg=True)
    elif field == "deadline":
        await state.set_state(NewTask.deadline)
        await cb.message.edit_text(t(lang, "nt_deadline"), reply_markup=deadline_kb(lang))
    elif field == "prio":
        await state.set_state(NewTask.prio)
        await cb.message.edit_text(t(lang, "nt_priority"), reply_markup=prio_kb(lang))
    elif field == "project":
        await ask_project(cb.message, state, u, lang, edit_cb=cb)
    elif field == "loc":
        d = await state.get_data()
        locs = await api.locations(uid, d.get("project_id")) if d.get("project_id") else []
        by_id = {l["id"]: l for l in locs}

        def label(l):
            parts, cur = [], l
            while cur:
                parts.append(cur["name"])
                cur = by_id.get(cur["parent_id"]) if cur.get("parent_id") else None
            return " · ".join(reversed(parts))
        items = [{"id": l["id"], "name": label(l)} for l in sorted(locs, key=lambda l: (l["parent_id"] or 0, l["sort_order"]))]
        await state.update_data(_locs=items)
        await state.set_state(NewTask.edit_loc)
        await cb.message.edit_text(t(lang, "nt_location"), reply_markup=list_kb(items, "ntl", skip_cb="ntl:0", skip_text=t(lang, "btn_skip")))
    elif field == "type":
        types = await api.task_types(uid)
        items = [{"id": x["id"], "name": f"{x['name']}" + (f" · {x['group_name']}" if x.get("group_name") else "")} for x in types]
        await state.update_data(_types=items)
        await state.set_state(NewTask.edit_type)
        await cb.message.edit_text(t(lang, "nt_type"), reply_markup=list_kb(items, "ntt"))


@router.callback_query(F.data.startswith("ntl_pg:"))
async def ntl_page(cb: CallbackQuery, state: FSMContext, lang: str):
    d = await state.get_data()
    await cb.message.edit_reply_markup(reply_markup=list_kb(d.get("_locs", []), "ntl", page=int(cb.data.split(":")[1]), skip_cb="ntl:0", skip_text=t(lang, "btn_skip")))
    await cb.answer()


@router.callback_query(F.data.startswith("ntl:"))
async def nt_loc(cb: CallbackQuery, state: FSMContext, u: dict, lang: str):
    lid = int(cb.data.split(":")[1])
    d = await state.get_data()
    name = next((x["name"] for x in d.get("_locs", []) if x["id"] == lid), None)
    await state.update_data(location_id=lid or None, location_name=name, _editing=False)
    await cb.answer()
    await show_confirm(cb, state, u["id"], lang, edit=True)


@router.callback_query(F.data.startswith("ntt_pg:"))
async def ntt_page(cb: CallbackQuery, state: FSMContext):
    d = await state.get_data()
    await cb.message.edit_reply_markup(reply_markup=list_kb(d.get("_types", []), "ntt", page=int(cb.data.split(":")[1])))
    await cb.answer()


@router.callback_query(F.data.startswith("ntt:"))
async def nt_type(cb: CallbackQuery, state: FSMContext, u: dict, lang: str):
    tid = int(cb.data.split(":")[1])
    d = await state.get_data()
    name = next((x["name"].split(" · ")[0] for x in d.get("_types", []) if x["id"] == tid), None)
    await state.update_data(type_id=tid, type_name=name, _editing=False)
    await cb.answer()
    await show_confirm(cb, state, u["id"], lang, edit=True)


@router.message(NewTask.edit_title, F.text)
async def nt_edit_title(msg: Message, state: FSMContext, u: dict, lang: str):
    await state.update_data(title=msg.text.strip()[:250], _editing=False)
    await msg.answer("✏️", reply_markup=main_menu(lang, perms_of(u), role_of(u)))
    await show_confirm(msg, state, u["id"], lang)


@router.message(NewTask.edit_desc, F.text)
async def nt_edit_desc(msg: Message, state: FSMContext, u: dict, lang: str):
    await state.update_data(description=msg.text.strip()[:2000], _editing=False)
    await msg.answer("✏️", reply_markup=main_menu(lang, perms_of(u), role_of(u)))
    await show_confirm(msg, state, u["id"], lang)


# ---- voice / free text -> task ----
@router.message(F.voice | F.audio)
async def voice_task(msg: Message, state: FSMContext, u: dict | None, lang: str, bot: Bot):
    if not u:
        return await msg.answer(t(lang, "not_linked"))
    if not _can_create(u):
        return await msg.answer(t(lang, "voice_no_perm"))
    cur = await state.get_state()
    if cur and cur.startswith("Report"):
        return  # photos-only flow; ignore voice
    wait = await msg.answer(t(lang, "voice_processing"))
    f = msg.voice or msg.audio
    buf = await bot.download(f)
    d = await state.get_data() if cur and cur.startswith("NewTask") else {}
    try:
        parsed = await api.voice_task(u["id"], buf.read(), lang, d.get("project_id"))
    except ApiError as e:
        await wait.delete()
        if e.code == "VOICE_NOT_CONFIGURED":
            return await msg.answer(t(lang, "voice_off"))
        return await err(msg, lang, e)
    await wait.delete()
    await _from_parsed(msg, state, u, lang, parsed)


async def _from_parsed(msg: Message, state: FSMContext, u: dict, lang: str, parsed: dict):
    await state.clear()
    data = {k: parsed.get(k) for k in ("transcript", "title", "description", "priority", "planned_start", "planned_end",
                                       "project_id", "project_name", "location_id", "location_name", "type_id", "type_name",
                                       "assignee_id", "assignee_name_heard", "assignee_candidates", "warnings")}
    data["reviewer_id"] = u["id"]
    if data.get("assignee_id"):
        c = next((c for c in parsed.get("assignee_candidates", []) if c["id"] == data["assignee_id"]), None)
        data["assignee_name"] = c["full_name"] if c else None
    await state.set_data(data)
    await _default_type(u["id"], data)
    await state.update_data(type_id=data.get("type_id"), type_name=data.get("type_name"))
    await _apply_default_reviewer(state, u)
    await show_confirm(msg, state, u["id"], lang)


@router.message(NewTask.confirm, F.text)
async def confirm_text_edit(msg: Message, state: FSMContext, u: dict, lang: str):
    """Free text while a card is shown: re-parse and merge (lets the manager say 'muddat 25.10' or 'Rustamga')."""
    d = await state.get_data()
    dt = parse_date(msg.text or "")
    if dt:
        return await _set_deadline(msg, state, u, lang, dt)
    try:
        parsed = await api.parse_task(u["id"], msg.text, lang, d.get("project_id"))
    except ApiError as e:
        return await err(msg, lang, e)
    # merge: only overwrite fields the new text actually specified
    upd = {}
    if parsed.get("assignee_id"):
        upd["assignee_id"], upd["assignee_candidates"] = parsed["assignee_id"], []
        c = next((c for c in parsed.get("assignee_candidates", []) if c["id"] == parsed["assignee_id"]), None)
        upd["assignee_name"] = c["full_name"] if c else None
    elif parsed.get("assignee_candidates"):
        upd["assignee_id"], upd["assignee_candidates"], upd["assignee_name_heard"] = None, parsed["assignee_candidates"], parsed.get("assignee_name_heard")
    if "no_deadline" not in (parsed.get("warnings") or []):
        upd["planned_end"] = parsed["planned_end"]
        upd["warnings"] = [w for w in (d.get("warnings") or []) if w != "no_deadline"]
    if parsed.get("location_id"):
        upd["location_id"], upd["location_name"] = parsed["location_id"], parsed["location_name"]
    if not d.get("title") or len((msg.text or "").split()) > 4 and not parsed.get("assignee_name_heard"):
        upd["title"] = parsed["title"]
    if parsed.get("priority") == "high":
        upd["priority"] = "high"
    await state.update_data(**upd)
    await show_confirm(msg, state, u["id"], lang)


# free text from a creator outside any flow -> treat as task instruction (long sentences only)
@router.message(F.text, ~F.text.startswith("/"))
async def free_text(msg: Message, state: FSMContext, u: dict | None, lang: str):
    if not u:
        # an unlinked user typing a bare 6-digit code links straight away
        if re.fullmatch(r"\s*\d{6}\s*", msg.text or ""):
            await state.set_state(Link.code)
            return await link_code(msg, state, lang)
        return await msg.answer(t(lang, "welcome_unlinked"))
    if await state.get_state():
        return
    words = (msg.text or "").split()
    if _can_create(u) and len(words) >= 4:
        wait = await msg.answer(t(lang, "type_text"))
        try:
            parsed = await api.parse_task(u["id"], msg.text, lang, None)
        except ApiError as e:
            await wait.delete()
            if e.code == "VOICE_NOT_CONFIGURED":
                return await msg.answer(t(lang, "voice_off"))
            return await err(msg, lang, e)
        await wait.delete()
        return await _from_parsed(msg, state, u, lang, parsed)
    await msg.answer(t(lang, "menu"), reply_markup=main_menu(lang, perms_of(u), role_of(u)))


# ============ outbox worker (notifications) ============
def _num(v) -> str:
    """12.0 -> '12', 12.5 -> '12.5'"""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    return str(int(f)) if f == int(f) else f"{f:g}"


def render_notification(lang: str, event: str, p: dict) -> str:
    if event == "digest":
        lines = [t(lang, "digest_title")]
        c = p.get("counts", {})

        def sect(key, items, fmt):
            if not items:
                return
            lines.append("\n" + t(lang, key, n=c.get(key.split("_")[1], len(items))))
            for it in items[:5]:
                lines.append(fmt(it))
            if len(items) > 5:
                lines.append(t(lang, "and_more", n=len(items) - 5))
        sect("digest_today", p.get("today", []), lambda i: f"• {i['code']} {i['title'][:40]}")
        sect("digest_overdue", p.get("overdue", []), lambda i: f"• {i['code']} {i['title'][:40]} ⏱{i['days']}")
        sect("digest_blocked", p.get("blocked", []), lambda i: f"• {i['code']} {i['title'][:40]} — {block_label(lang, i.get('reason'))}")
        sect("digest_review", p.get("review", []), lambda i: f"• {i['code']} {i['title'][:40]}")
        if p.get("urgent"):
            lines.append("\n" + t(lang, "digest_urgent"))
            for i in p["urgent"]:
                lines.append(f"🔥 {i['code']} {i['title'][:40]} · {fmt_date(i['planned_end'])}")
        if p.get("queue_count"):
            lines.append("\n" + t(lang, "digest_queue", n=p["queue_count"], d=p.get("queue_oldest_days", 0)))
        return "\n".join(lines)
    if event == "daily_report":
        workers = t(lang, "dr_workers", n=p["workers"]) if p.get("workers") else ""
        note = f"\n📝 {p['note']}" if p.get("note") else ""
        total = ""
        if p.get("total") is not None:
            plan = f" / {_num(p['plan'])} {p.get('unit') or ''}" if p.get("plan") else ""
            total = t(lang, "dr_total", total=f"{_num(p['total'])} {p.get('unit') or ''}".strip(), plan=plan)
        if p.get("duplicate"):
            note += "\n⚠️ " + t(lang, "report_dup")
        return t(lang, "n_daily_report", code=p.get("code", ""), title=p.get("title", ""), by=p.get("by", ""),
                 date=fmt_date(p.get("date")), quantity=_num(p.get("quantity")) if p.get("quantity") is not None else "—",
                 unit=p.get("unit") or "", workers=workers, note=note, total=total)
    key = f"n_{event}"
    fields = dict(code=p.get("code", ""), title=p.get("title", ""), planned_end=fmt_date(p.get("planned_end")),
                  assigned_by=p.get("assigned_by", ""), days=p.get("days", ""), reason=block_label(lang, p.get("reason")) if event in ("blocked", "blocked_24h") else (p.get("reason") or ""),
                  note=p.get("note", ""), by=p.get("by", ""), text=p.get("text", ""))
    s = t(lang, key, **fields)
    return s if s != key else f"🔔 {event} {p.get('code', '')}\n{p.get('title', '')}"


async def outbox_worker(bot: Bot):
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    while True:
        try:
            items = await api.outbox()
            sent, failed = [], []
            for n in items:
                lang = n.get("lang") or "uz"
                text = render_notification(lang, n["event"], n.get("payload") or {})
                kb = None
                if n.get("task_id"):
                    b = InlineKeyboardBuilder()
                    b.row(InlineKeyboardButton(text="📋 " + n["payload"].get("code", ""), callback_data=f"t:show:{n['task_id']}"))
                    kb = b.as_markup()
                try:
                    await bot.send_message(n["telegram_user_id"], text[:4000], reply_markup=kb,
                                           disable_notification=not (n.get("payload") or {}).get("urgent", False) and _quiet_hours())
                    sent.append(n["id"])
                except Exception as e:  # blocked bot, deleted account...
                    log.warning("send failed to %s: %s", n["telegram_user_id"], e)
                    failed.append(n["id"])
                await asyncio.sleep(0.05)
            if sent or failed:
                await api.outbox_ack(sent, failed)
        except Exception as e:
            log.warning("outbox loop error: %s", e)
        await asyncio.sleep(settings.OUTBOX_INTERVAL)


def _quiet_hours() -> bool:
    """22:00–07:00 Tashkent: non-urgent messages are sent silently."""
    try:
        from zoneinfo import ZoneInfo
        h = datetime.now(ZoneInfo(settings.TZ_NAME)).hour
    except Exception:
        h = datetime.utcnow().hour + 5
    return h >= 22 or h < 7


# ============ app ============
async def main():
    bot = Bot(settings.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    storage = None
    try:
        from aiogram.fsm.storage.redis import RedisStorage
        storage = RedisStorage.from_url(settings.REDIS_URL, state_ttl=1800, data_ttl=1800)
        await storage.redis.ping()
    except Exception as e:
        log.warning("Redis storage unavailable (%s) — using memory storage", e)
        from aiogram.fsm.storage.memory import MemoryStorage
        storage = MemoryStorage()
    dp = Dispatcher(storage=storage)
    dp.update.outer_middleware(UserMiddleware())
    dp.include_router(router)

    try:
        who = await bot.me()
        if who.username:
            await api.register_username(who.username)
            log.info("bot username: @%s", who.username)
    except Exception as e:
        log.warning("username ro'yxatdan o'tmadi: %s", e)

    from aiogram.types import BotCommand
    await bot.set_my_commands([BotCommand(command="vazifalarim", description="Vazifalarim / Мои задачи"),
                               BotCommand(command="hisobot", description="Kunlik hisobot / Отчёт"),
                               BotCommand(command="muammo", description="Bloklash / Проблема"),
                               BotCommand(command="yangi", description="Yangi vazifa / Новая задача"),
                               BotCommand(command="qidir", description="Kod bo'yicha / По коду"),
                               BotCommand(command="til", description="Til / Язык / Language"),
                               BotCommand(command="help", description="Yordam / Помощь")])
    asyncio.create_task(outbox_worker(bot))

    if settings.BOT_MODE == "webhook" and settings.WEBHOOK_URL:
        from aiohttp import web
        from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
        await bot.set_webhook(settings.WEBHOOK_URL, secret_token=settings.WEBHOOK_SECRET, drop_pending_updates=False)
        app = web.Application()
        SimpleRequestHandler(dispatcher=dp, bot=bot, secret_token=settings.WEBHOOK_SECRET).register(app, path="/telegram/webhook")
        setup_application(app, dp, bot=bot)
        log.info("webhook mode on :%s", settings.WEBHOOK_PORT)
        runner = web.AppRunner(app)
        await runner.setup()
        await web.TCPSite(runner, "0.0.0.0", settings.WEBHOOK_PORT).start()
        await asyncio.Event().wait()
    else:
        await bot.delete_webhook(drop_pending_updates=False)
        log.info("polling mode")
        await dp.start_polling(bot, allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    asyncio.run(main())
