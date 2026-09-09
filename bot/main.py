"""SAFF Vazifalar boti 2.0.

Ikki xil foydalanuvchi:
  * boshliq / assistant — vazifa beradi (ovoz yoki matn), topshirilganini qabul qiladi,
    kechikkanlarni va hisobotni ko'radi;
  * bo'lim boshlig'i / ijrochi — o'z vazifalarini ko'radi va **dalil bilan** topshiradi.
"""
from __future__ import annotations

import asyncio
import html
import logging
import re
from datetime import date, datetime, timedelta
from difflib import SequenceMatcher
from typing import Any, Optional

from aiogram import BaseMiddleware, Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest, TelegramConflictError, TelegramUnauthorizedError
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, Message, ReplyKeyboardRemove, TelegramObject

from api import ApiError, api
from config import settings
from i18n import T, field_label, field_of, role_label, t
from render import (cancel_kb, confirm_card, confirm_kb, due_kb, edit_block_kb, edit_menu_kb,
                    fmt_due, lang_kb, list_kb, main_menu, notif_kb, notif_text, people_text,
                    report_kb, task_block, task_card, task_kb)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("bot")

router = Router()
MANAGERS = ("boss", "assistant")


# ============ foydalanuvchi ============
class UserMiddleware(BaseMiddleware):
    """data['u'] (API foydalanuvchisi yoki None) va data['lang'] qo'shadi."""
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
                    log.warning("foydalanuvchi topilmadi: %s", e)
                    u = hit[1] if hit else None
                self.cache[tg_user.id] = (now + 30, u)
        data["u"] = u
        lang = (u or {}).get("lang") or ((tg_user.language_code or "uz")[:2] if tg_user else "uz")
        data["lang"] = lang if lang in T else "uz"
        return await handler(event, data)

    @classmethod
    def invalidate(cls, tg_id: int):
        cls.cache.pop(tg_id, None)


def role_of(u: dict | None) -> str:
    return (u or {}).get("role") or ""


def is_manager(u: dict | None) -> bool:
    return role_of(u) in MANAGERS


def is_cancel(msg: Message) -> bool:
    txt = (msg.text or "").strip()
    return txt in {T[x]["btn_cancel"] for x in T} or txt in ("/cancel", "/bekor")


async def err(target, lang: str, e: ApiError):
    text = t(lang, "err", msg=e.message)
    if isinstance(target, CallbackQuery):
        await target.answer(e.message[:190], show_alert=True)
    else:
        await target.answer(text)


async def menu(msg: Message, u: dict, lang: str, text: str | None = None):
    await msg.answer(text or t(lang, "menu"), reply_markup=main_menu(lang, role_of(u)))


# ============ holatlar ============
class Link(StatesGroup):
    code = State()


class NewTask(StatesGroup):
    who = State()
    title = State()
    due = State()
    due_custom = State()
    confirm = State()
    edit_all = State()
    edit_title = State()
    edit_desc = State()


class Submit(StatesGroup):
    note = State()
    files = State()


class Ret(StatesGroup):
    reason = State()


class Comment(StatesGroup):
    text = State()


# ============ sana ============
_TIME_TAIL = ("kechgacha", "kechqurun", "kechga", "kechasi", "ertalabgacha", "ertalab",
              "kunduzi", "gacha", "kunga", "kuni", "до вечера", "вечером", "к вечеру",
              "by evening", "end of day", "eod")
_WORDS = {
    0: ("bugun", "shu kun", "сегодня", "today"),
    1: ("ertaga", "erta", "завтра", "tomorrow"),
    2: ("indinga", "indin", "birinkun", "послезавтра"),
    7: ("hafta", "bir hafta", "keyingi hafta", "неделя", "через неделю", "week", "next week"),
}


def _word_date(s: str) -> Optional[date]:
    n = " ".join(re.sub(r"[^0-9a-zа-яё\s'ʻ’]+", " ", (s or "").lower()).split())
    if not n:
        return None
    for tail in sorted(_TIME_TAIL, key=len, reverse=True):
        if n.endswith(" " + tail) or n == tail:
            n = n[: len(n) - len(tail)].strip()
            break
    for days, words in _WORDS.items():
        if n in words:
            return date.today() + timedelta(days=days)
    m = re.fullmatch(r"(?:через\s+|in\s+)?(\d{1,3})\s*(kun(?:dan|ga|da)?|дн(?:я|ей)?|days?)", n)
    if m:
        return date.today() + timedelta(days=int(m.group(1)))
    return None


def parse_due(s: str) -> Optional[str]:
    """«ertaga», «15.09.2026», «15.09.2026 14:00» -> ISO satr. Soat berilmasa 18:00."""
    s = (s or "").strip()
    if not s:
        return None
    hour, minute = 18, 0
    # Soat faqat ikki nuqta bilan: "14:00". Nuqta sanaga tegishli ("15.09.2026"),
    # aks holda "15.09" soat deb o'qilib, sana buzilardi.
    m = re.search(r"\b(\d{1,2}):(\d{2})\b", s)
    if m:
        h, mi = int(m.group(1)), int(m.group(2))
        if h <= 23 and mi <= 59:
            hour, minute = h, mi
            s = (s[:m.start()] + " " + s[m.end():]).strip()
    w = _word_date(s)
    if w:
        return datetime.combine(w, datetime.min.time()).replace(hour=hour, minute=minute).isoformat(timespec="minutes")
    for fmt in ("%d.%m.%Y", "%d.%m.%y", "%d.%m", "%Y-%m-%d", "%d/%m/%Y", "%d/%m"):
        try:
            d = datetime.strptime(s.strip(), fmt).date()
        except ValueError:
            continue
        if "%Y" not in fmt and "%y" not in fmt:
            d = d.replace(year=date.today().year)
            if d < date.today() - timedelta(days=30):
                d = d.replace(year=d.year + 1)
        return datetime.combine(d, datetime.min.time()).replace(hour=hour, minute=minute).isoformat(timespec="minutes")
    return None


# ============ start / bog'lash ============
@router.message(CommandStart())
async def start(msg: Message, state: FSMContext, u: dict | None, lang: str,
                command: CommandObject = None):
    await state.clear()
    arg = (command.args or "").strip() if command else ""
    if u:
        return await menu(msg, u, lang, t(lang, "linked", name=u["full_name"],
                                          role=role_label(lang, u["role"])))
    if re.fullmatch(r"\d{6}", arg):
        await state.set_state(Link.code)
        msg.text = arg
        return await link_code(msg, state, lang)
    await msg.answer(t(lang, "welcome_unlinked"), reply_markup=ReplyKeyboardRemove())
    await state.set_state(Link.code)
    await msg.answer(t(lang, "ask_code"))


@router.message(Link.code, F.text)
async def link_code(msg: Message, state: FSMContext, lang: str):
    code = (msg.text or "").strip()
    if not re.fullmatch(r"\d{6}", code):
        return await msg.answer(t(lang, "ask_code"))
    try:
        u = await api.consume_code(code, msg.from_user.id)
    except ApiError:
        return await msg.answer(t(lang, "code_invalid"))
    await state.clear()
    UserMiddleware.invalidate(msg.from_user.id)
    lang = u.get("lang") or lang
    await menu(msg, u, lang, t(lang, "linked", name=u["full_name"], role=role_label(lang, u["role"])))


@router.message(Command("menu"))
async def cmd_menu(msg: Message, state: FSMContext, u: dict | None, lang: str):
    await state.clear()
    if not u:
        return await msg.answer(t(lang, "not_linked"))
    await menu(msg, u, lang)


@router.message(Command("help"))
async def cmd_help(msg: Message, lang: str):
    await msg.answer(t(lang, "help"))


@router.message(F.text.in_({T[x]["btn_cancel"] for x in T}))
async def cancel_any(msg: Message, state: FSMContext, u: dict | None, lang: str):
    await state.clear()
    if not u:
        return await msg.answer(t(lang, "not_linked"))
    await menu(msg, u, lang, t(lang, "cancelled"))


@router.message(F.text.in_({T[x]["btn_lang"] for x in T}))
async def ask_lang(msg: Message, lang: str):
    await msg.answer(t(lang, "lang_ask"), reply_markup=lang_kb())


@router.callback_query(F.data.startswith("lang:"))
async def set_lang(cb: CallbackQuery, u: dict | None, lang: str):
    new = cb.data.split(":")[1]
    if u:
        await api.set_lang(u["id"], new)
        UserMiddleware.invalidate(cb.from_user.id)
        u = {**u, "lang": new}
    await cb.message.answer(t(new, "lang_set"), reply_markup=main_menu(new, role_of(u)))
    await cb.answer()


# ============ ro'yxatlar ============
async def show_list(msg: Message, u: dict, lang: str, rows: list[dict], empty_key="nothing"):
    if not rows:
        return await msg.answer(t(lang, empty_key))
    for tk in rows[:10]:
        await msg.answer(task_card(lang, tk), reply_markup=task_kb(lang, tk))
    if len(rows) > 10:
        await msg.answer(f"… +{len(rows) - 10}")


@router.message(F.text.in_({T[x]["btn_my"] for x in T}))
async def my_tasks(msg: Message, u: dict | None, lang: str):
    if not u:
        return await msg.answer(t(lang, "not_linked"))
    rows = (await api.tasks(u["id"], status="new,progress", per_page=20))["items"]
    await show_list(msg, u, lang, rows)


@router.message(F.text.in_({T[x]["btn_submitted"] for x in T}))
async def submitted_list(msg: Message, u: dict | None, lang: str):
    if not u or not is_manager(u):
        return await msg.answer(t(lang, "no_perm"))
    rows = (await api.tasks(u["id"], status="submitted", per_page=20))["items"]
    await show_list(msg, u, lang, rows)


@router.message(F.text.in_({T[x]["btn_late"] for x in T}))
async def late_list(msg: Message, u: dict | None, lang: str):
    if not u or not is_manager(u):
        return await msg.answer(t(lang, "no_perm"))
    rows = (await api.tasks(u["id"], overdue=True, per_page=20))["items"]
    await show_list(msg, u, lang, rows)


@router.message(F.text.in_({T[x]["btn_people"] for x in T}))
async def people_list(msg: Message, u: dict | None, lang: str):
    if not u or not is_manager(u):
        return await msg.answer(t(lang, "no_perm"))
    rows = await api.users(u["id"], active=True, limit=200)
    rows = [x for x in rows if x["role"] not in MANAGERS]
    if not rows:
        return await msg.answer(t(lang, "nothing"))
    text = people_text(lang, rows)
    for chunk in [text[i:i + 3500] for i in range(0, len(text), 3500)]:
        await msg.answer(chunk)


# ============ hisobot ============
async def send_report(target, u: dict, lang: str, period: str, edit=False):
    rep = await api.report(u["id"], period=period)
    text = t(lang, "rep_head", **{"from": rep["date_from"], "to": rep["date_to"]},
             table=html.escape(rep["table"]))
    kb = report_kb(lang, period)
    m = target.message if isinstance(target, CallbackQuery) else target
    if edit and isinstance(target, CallbackQuery):
        try:
            return await m.edit_text(text, reply_markup=kb)
        except TelegramBadRequest:
            pass
    await m.answer(text, reply_markup=kb)


@router.message(F.text.in_({T[x]["btn_report"] for x in T}))
async def report_cmd(msg: Message, u: dict | None, lang: str):
    if not u or not is_manager(u):
        return await msg.answer(t(lang, "no_perm"))
    await send_report(msg, u, lang, "month")


@router.callback_query(F.data.startswith("rep:dl:"))
async def report_download(cb: CallbackQuery, u: dict, lang: str):
    _, _, fmt, period = cb.data.split(":")
    await cb.answer()
    data = await api.report_file(u["id"], period=period, fmt=fmt)
    ext = "xlsx" if fmt == "xlsx" else "csv"
    await cb.message.answer_document(
        BufferedInputFile(data, filename=f"saff-hisobot-{period}.{ext}"),
        caption=t(lang, "rep_file"))


@router.callback_query(F.data.startswith("rep:"))
async def report_period(cb: CallbackQuery, u: dict, lang: str):
    await cb.answer()
    await send_report(cb, u, lang, cb.data.split(":")[1], edit=True)


# ============ vazifa amallari ============
@router.callback_query(F.data.startswith("t:"))
async def task_action(cb: CallbackQuery, state: FSMContext, u: dict | None, lang: str):
    if not u:
        return await cb.answer(t(lang, "not_linked"), show_alert=True)
    _, action, tid = cb.data.split(":")
    tid = int(tid)
    try:
        if action == "open":
            tk = await api.task(u["id"], tid)
            await cb.message.answer(task_card(lang, tk), reply_markup=task_kb(lang, tk))
        elif action == "start":
            tk = await api.start(u["id"], tid)
            await cb.message.answer(t(lang, "started", code=tk["code"]))
        elif action == "acc":
            tk = await api.accept(u["id"], tid)
            await cb.message.answer(t(lang, "accepted", code=tk["code"]))
        elif action == "ret":
            await state.set_state(Ret.reason)
            await state.update_data(task_id=tid)
            await cb.message.answer(t(lang, "ret_reason"), reply_markup=cancel_kb(lang))
        elif action == "cm":
            await state.set_state(Comment.text)
            await state.update_data(task_id=tid)
            await cb.message.answer(t(lang, "cm_ask"), reply_markup=cancel_kb(lang))
        elif action == "sub":
            await begin_submit(cb.message, state, u, lang, tid)
    except ApiError as e:
        return await err(cb, lang, e)
    await cb.answer()


@router.message(Ret.reason, F.text)
async def ret_reason(msg: Message, state: FSMContext, u: dict, lang: str):
    if is_cancel(msg):
        return await cancel_any(msg, state, u, lang)
    tid = (await state.get_data())["task_id"]
    await state.clear()
    try:
        tk = await api.return_task(u["id"], tid, msg.text.strip())
    except ApiError as e:
        return await err(msg, lang, e)
    await menu(msg, u, lang, t(lang, "returned", code=tk["code"]))


@router.message(Comment.text, F.text)
async def comment_text(msg: Message, state: FSMContext, u: dict, lang: str):
    if is_cancel(msg):
        return await cancel_any(msg, state, u, lang)
    tid = (await state.get_data())["task_id"]
    await state.clear()
    try:
        await api.comment(u["id"], tid, msg.text.strip())
    except ApiError as e:
        return await err(msg, lang, e)
    await menu(msg, u, lang, t(lang, "cm_ok"))


# ============ topshirish (dalil bilan) ============
@router.message(F.text.in_({T[x]["btn_submit"] for x in T}))
async def submit_pick(msg: Message, state: FSMContext, u: dict | None, lang: str):
    if not u:
        return await msg.answer(t(lang, "not_linked"))
    rows = (await api.tasks(u["id"], status="new,progress", per_page=20))["items"]
    if not rows:
        return await msg.answer(t(lang, "sb_none"))
    items = [{"id": r["id"], "name": f"{r['code']} {r['title'][:40]}"} for r in rows]
    await state.update_data(_pick=items)
    await msg.answer(t(lang, "sb_pick"), reply_markup=list_kb(items, "sbp"))


@router.callback_query(F.data.startswith("sbp_pg:"))
async def submit_page(cb: CallbackQuery, state: FSMContext):
    d = await state.get_data()
    await cb.message.edit_reply_markup(
        reply_markup=list_kb(d.get("_pick", []), "sbp", page=int(cb.data.split(":")[1])))
    await cb.answer()


@router.callback_query(F.data.startswith("sbp:"))
async def submit_chosen(cb: CallbackQuery, state: FSMContext, u: dict, lang: str):
    await cb.answer()
    await begin_submit(cb.message, state, u, lang, int(cb.data.split(":")[1]))


async def begin_submit(msg: Message, state: FSMContext, u: dict, lang: str, task_id: int):
    await state.clear()
    await state.set_state(Submit.note)
    await state.update_data(task_id=task_id, files=0)
    await msg.answer(t(lang, "sb_note"), reply_markup=cancel_kb(lang))


@router.message(Submit.note, F.text)
async def submit_note(msg: Message, state: FSMContext, u: dict, lang: str):
    if is_cancel(msg):
        return await cancel_any(msg, state, u, lang)
    await state.update_data(note=msg.text.strip()[:2000])
    await state.set_state(Submit.files)
    await msg.answer(t(lang, "sb_files"), reply_markup=cancel_kb(lang, done=True))


@router.message(Submit.files, F.photo | F.document)
async def submit_file(msg: Message, state: FSMContext, u: dict, lang: str, bot: Bot):
    d = await state.get_data()
    if msg.photo:
        f, name, mime = msg.photo[-1], f"dalil_{msg.message_id}.jpg", "image/jpeg"
    else:
        f, name = msg.document, msg.document.file_name or f"dalil_{msg.message_id}"
        mime = msg.document.mime_type or "application/octet-stream"
    buf = await bot.download(f)
    try:
        await api.upload(u["id"], d["task_id"], buf.read(), name, mime, kind="proof")
    except ApiError as e:
        return await err(msg, lang, e)
    n = d.get("files", 0) + 1
    await state.update_data(files=n)
    await msg.answer(t(lang, "sb_got", n=n), reply_markup=cancel_kb(lang, done=True))


@router.message(Submit.files, F.text)
async def submit_finish(msg: Message, state: FSMContext, u: dict, lang: str):
    if is_cancel(msg):
        return await cancel_any(msg, state, u, lang)
    if (msg.text or "").strip() not in {T[x]["btn_done"] for x in T}:
        return await msg.answer(t(lang, "sb_files"), reply_markup=cancel_kb(lang, done=True))
    d = await state.get_data()
    if not d.get("files"):
        return await msg.answer(t(lang, "sb_need_file"), reply_markup=cancel_kb(lang, done=True))
    await state.clear()
    try:
        tk = await api.submit(u["id"], d["task_id"], d.get("note") or "—")
    except ApiError as e:
        return await err(msg, lang, e)
    await menu(msg, u, lang, t(lang, "sb_ok", code=tk["code"]))


# ============ yangi vazifa ============
@router.message(Command("yangi", "new"))
@router.message(F.text.in_({T[x]["btn_new"] for x in T}))
async def new_task(msg: Message, state: FSMContext, u: dict | None, lang: str):
    if not u:
        return await msg.answer(t(lang, "not_linked"))
    if not is_manager(u):
        return await msg.answer(t(lang, "no_perm"))
    await state.clear()
    await ask_who(msg, state, u, lang)


async def _people(u: dict) -> list[dict]:
    rows = await api.users(u["id"], active=True, limit=200)
    return [{"id": x["id"], "name": f"{x['full_name']}"
             + (f" · {x['department_name']}" if x.get("department_name") else
                (f" · {x['position']}" if x.get("position") else ""))}
            for x in rows if x["id"] != u["id"]]


async def ask_who(msg: Message, state: FSMContext, u: dict, lang: str):
    items = await _people(u)
    await state.set_state(NewTask.who)
    await state.update_data(_people=items)
    await msg.answer(t(lang, "nt_who"), reply_markup=list_kb(items, "ntw"))


@router.callback_query(F.data.startswith("ntw_pg:"))
async def who_page(cb: CallbackQuery, state: FSMContext):
    d = await state.get_data()
    await cb.message.edit_reply_markup(
        reply_markup=list_kb(d.get("_people", []), "ntw", page=int(cb.data.split(":")[1])))
    await cb.answer()


@router.callback_query(F.data.startswith("ntw:"))
async def who_chosen(cb: CallbackQuery, state: FSMContext, u: dict, lang: str):
    uid = int(cb.data.split(":")[1])
    d = await state.get_data()
    name = next((x["name"].split(" · ")[0] for x in d.get("_people", []) if x["id"] == uid), None)
    await state.update_data(assignee_id=uid, assignee_name=name, assignee_candidates=[])
    await cb.answer()
    if d.get("title"):
        return await show_confirm(cb, state, u, lang, edit=True)
    await state.set_state(NewTask.title)
    await cb.message.answer(t(lang, "nt_title"), reply_markup=cancel_kb(lang))


@router.message(NewTask.title, F.text)
async def nt_title(msg: Message, state: FSMContext, u: dict, lang: str):
    if is_cancel(msg):
        return await cancel_any(msg, state, u, lang)
    await state.update_data(title=msg.text.strip()[:250])
    d = await state.get_data()
    if d.get("due_at"):
        return await show_confirm(msg, state, u, lang)
    await state.set_state(NewTask.due)
    await msg.answer(t(lang, "nt_due"), reply_markup=due_kb(lang))


@router.callback_query(F.data.startswith("nt:due:"))
async def nt_due(cb: CallbackQuery, state: FSMContext, u: dict, lang: str):
    v = cb.data.split(":")[2]
    await cb.answer()
    if v == "custom":
        await state.set_state(NewTask.due_custom)
        return await cb.message.answer(t(lang, "nt_due_custom"), reply_markup=cancel_kb(lang))
    due = datetime.combine(date.today() + timedelta(days=int(v)), datetime.min.time())
    await state.update_data(due_at=due.replace(hour=18).isoformat(timespec="minutes"))
    await show_confirm(cb, state, u, lang)


@router.message(NewTask.due_custom, F.text)
async def nt_due_custom(msg: Message, state: FSMContext, u: dict, lang: str):
    if is_cancel(msg):
        return await cancel_any(msg, state, u, lang)
    due = parse_due(msg.text or "")
    if not due:
        return await msg.answer(t(lang, "nt_bad_date"))
    await state.update_data(due_at=due)
    await show_confirm(msg, state, u, lang)


async def show_confirm(target, state: FSMContext, u: dict, lang: str, edit=False):
    d = await state.get_data()
    await state.set_state(NewTask.confirm)
    text, kb = confirm_card(lang, d), confirm_kb(lang, d)
    m = target.message if isinstance(target, CallbackQuery) else target
    if edit and isinstance(target, CallbackQuery):
        try:
            return await m.edit_text(text, reply_markup=kb)
        except TelegramBadRequest:
            pass
    await m.answer(text, reply_markup=kb)


@router.callback_query(F.data.startswith("nt:pick:"))
async def nt_pick(cb: CallbackQuery, state: FSMContext, u: dict, lang: str):
    uid = int(cb.data.split(":")[2])
    d = await state.get_data()
    name = next((c["full_name"] for c in d.get("assignee_candidates", []) if c["id"] == uid), None)
    await state.update_data(assignee_id=uid, assignee_name=name, assignee_candidates=[])
    await cb.answer()
    await show_confirm(cb, state, u, lang, edit=True)


@router.callback_query(F.data == "nt:send")
async def nt_send(cb: CallbackQuery, state: FSMContext, u: dict, lang: str):
    d = await state.get_data()
    body = {"title": d.get("title"), "assignee_id": d.get("assignee_id"),
            "due_at": d.get("due_at"), "description": d.get("description")}
    try:
        tk = await api.create_task(u["id"], body)
    except ApiError as e:
        return await err(cb, lang, e)
    await state.clear()
    await cb.message.edit_text(t(lang, "created", code=tk["code"], title=tk["title"],
                                 assignee=tk["assignee_name"], due=fmt_due(tk["due_at"], lang)))
    await cb.answer()


@router.callback_query(F.data == "nt:cancel")
async def nt_cancel(cb: CallbackQuery, state: FSMContext, lang: str):
    await state.clear()
    await cb.message.edit_text(t(lang, "cancelled"))
    await cb.answer()


@router.callback_query(F.data == "nt:back")
async def nt_back(cb: CallbackQuery, state: FSMContext, u: dict, lang: str):
    await cb.answer()
    await show_confirm(cb, state, u, lang, edit=True)


# ---- tahrirlash: vazifa oddiy matn bo'lib chiqadi ----
_EMPTY = {"", "—", "-", "–", "yoq", "нет", "none", "null"}


def _norm(s: str) -> str:
    s = (s or "").lower().strip()
    for a, b in (("ʻ", ""), ("’", ""), ("'", ""), ("`", ""), ("ў", "u"), ("қ", "q"),
                 ("ғ", "g"), ("ҳ", "h")):
        s = s.replace(a, b)
    s = s.replace("sh", "s").replace("ch", "c").replace("x", "h")
    return " ".join(re.sub(r"[^0-9a-zа-яё ]+", " ", s).split())


def _is_empty(v: str) -> bool:
    return _norm(v) in _EMPTY


def parse_block(text: str) -> dict[str, str]:
    """«Sarlavha: ...» ko'rinishidagi matnni maydonlarga ajratadi."""
    out: dict[str, str] = {}
    cur: Optional[str] = None
    for raw in (text or "").splitlines():
        line = raw.strip()
        if ":" in line:
            k, v = line.split(":", 1)
            f = field_of(k)
            if f:
                out[f], cur = v.strip(), f
                continue
        if cur and line:
            out[cur] = (out[cur] + " " + line).strip()
    return out


def _match_person(q: str, people: list[dict]) -> tuple[Optional[dict], list[dict]]:
    n = _norm(q)
    if not n or not people:
        return None, []
    for pick in (lambda p: _norm(p["name"].split(" · ")[0]) == n,
                 lambda p: n in _norm(p["name"]).split() or _norm(p["name"]).startswith(n)):
        hits = [p for p in people if pick(p)]
        if len(hits) == 1:
            return hits[0], []
        if hits:
            return None, hits
    scored = sorted(((SequenceMatcher(None, n, _norm(p["name"])).ratio(), i, p)
                     for i, p in enumerate(people)), key=lambda x: -x[0])
    if scored and scored[0][0] >= 0.72:
        if len(scored) > 1 and scored[1][0] >= scored[0][0] - 0.04:
            return None, [scored[0][2], scored[1][2]]
        return scored[0][2], []
    return None, []


async def apply_block(state: FSMContext, u: dict, lang: str, text: str) -> Optional[list[str]]:
    """Tahrirlangan matnni qo'llaydi. Blok emas bo'lsa None — matn erkin gap sifatida o'qiladi."""
    f = parse_block(text)
    if not f:
        return None
    d = await state.get_data()
    upd: dict[str, Any] = {}
    notes: list[str] = []

    def bad(key: str, v: str):
        notes.append(t(lang, "e_nf", field=field_label(lang, key), value=(v or "—")[:60]))

    if "title" in f:
        if _is_empty(f["title"]):
            bad("title", f["title"])
        else:
            upd["title"] = f["title"][:250]
    if "description" in f:
        upd["description"] = None if _is_empty(f["description"]) else f["description"][:2000]
    if "due" in f:
        if _is_empty(f["due"]):
            upd["due_at"] = None
        else:
            due = parse_due(f["due"])
            if due:
                upd["due_at"] = due
            else:
                bad("due", f["due"])
    if "assignee" in f and _norm(f["assignee"]) != _norm(d.get("assignee_name") or ""):
        if _is_empty(f["assignee"]):
            upd.update(assignee_id=None, assignee_name=None, assignee_candidates=[])
        else:
            people = await _people(u)
            person, amb = _match_person(f["assignee"], people)
            if person:
                upd.update(assignee_id=person["id"],
                           assignee_name=person["name"].split(" · ")[0], assignee_candidates=[])
            elif amb:
                upd.update(assignee_id=None, assignee_name=None,
                           assignee_name_heard=f["assignee"],
                           assignee_candidates=[{"id": p["id"],
                                                 "full_name": p["name"].split(" · ")[0],
                                                 "hint": (p["name"].split(" · ") + [""])[1],
                                                 "score": 90} for p in amb[:3]])
            else:
                bad("assignee", f["assignee"])
    await state.update_data(**upd)
    return notes


@router.callback_query(F.data == "nt:edit")
async def nt_edit(cb: CallbackQuery, state: FSMContext, u: dict, lang: str):
    d = await state.get_data()
    block = task_block(lang, d)
    await state.set_state(NewTask.edit_all)
    await cb.message.answer(
        f"{t(lang, 'e_block_head')}\n\n<pre>{html.escape(block)}</pre>{t(lang, 'e_block_tip')}",
        reply_markup=edit_block_kb(lang, block))
    await cb.answer()


@router.callback_query(F.data == "nt:fields")
async def nt_fields(cb: CallbackQuery, lang: str):
    await cb.message.edit_reply_markup(reply_markup=edit_menu_kb(lang))
    await cb.answer()


@router.callback_query(F.data.startswith("nt:edit:"))
async def nt_edit_field(cb: CallbackQuery, state: FSMContext, u: dict, lang: str):
    field = cb.data.split(":")[2]
    await cb.answer()
    if field == "assignee":
        return await ask_who(cb.message, state, u, lang)
    if field == "due":
        await state.set_state(NewTask.due)
        return await cb.message.answer(t(lang, "nt_due"), reply_markup=due_kb(lang))
    if field == "title":
        await state.set_state(NewTask.edit_title)
        cur = (await state.get_data()).get("title") or ""
        return await cb.message.answer(t(lang, "e_title_now", cur=cur), reply_markup=cancel_kb(lang))
    if field == "desc":
        await state.set_state(NewTask.edit_desc)
        return await cb.message.answer(t(lang, "e_desc_ask"), reply_markup=cancel_kb(lang))


@router.message(NewTask.edit_title, F.text)
async def nt_edit_title(msg: Message, state: FSMContext, u: dict, lang: str):
    if is_cancel(msg):
        return await cancel_any(msg, state, u, lang)
    await state.update_data(title=msg.text.strip()[:250])
    await msg.answer("✏️", reply_markup=main_menu(lang, role_of(u)))
    await show_confirm(msg, state, u, lang)


@router.message(NewTask.edit_desc, F.text)
async def nt_edit_desc(msg: Message, state: FSMContext, u: dict, lang: str):
    if is_cancel(msg):
        return await cancel_any(msg, state, u, lang)
    await state.update_data(description=msg.text.strip()[:2000])
    await msg.answer("✏️", reply_markup=main_menu(lang, role_of(u)))
    await show_confirm(msg, state, u, lang)


@router.message(NewTask.edit_all, F.text)
async def nt_edit_all(msg: Message, state: FSMContext, u: dict, lang: str):
    if is_cancel(msg):
        return await cancel_any(msg, state, u, lang)
    notes = await apply_block(state, u, lang, msg.text)
    if notes is None:
        return await merge_free_text(msg, state, u, lang)
    if notes:
        await msg.answer("\n".join(notes))
    await show_confirm(msg, state, u, lang)


@router.message(NewTask.confirm, F.text)
async def confirm_text(msg: Message, state: FSMContext, u: dict, lang: str):
    if is_cancel(msg):
        return await cancel_any(msg, state, u, lang)
    notes = await apply_block(state, u, lang, msg.text)
    if notes is not None:
        if notes:
            await msg.answer("\n".join(notes))
        return await show_confirm(msg, state, u, lang)
    await merge_free_text(msg, state, u, lang)


async def merge_free_text(msg: Message, state: FSMContext, u: dict, lang: str):
    """Karta turganda kelgan oddiy gap: sana bo'lsa muddat, aks holda modeldan o'qiymiz."""
    due = parse_due(msg.text or "")
    if due:
        await state.update_data(due_at=due)
        return await show_confirm(msg, state, u, lang)
    try:
        parsed = await api.parse_task(u["id"], msg.text, lang)
    except ApiError as e:
        return await err(msg, lang, e)
    upd = {}
    if parsed.get("assignee_id"):
        upd["assignee_id"] = parsed["assignee_id"]
        c = next((c for c in parsed.get("assignee_candidates", [])
                  if c["id"] == parsed["assignee_id"]), None)
        upd["assignee_name"] = c["full_name"] if c else None
        upd["assignee_candidates"] = []
    elif parsed.get("assignee_candidates"):
        upd.update(assignee_id=None, assignee_candidates=parsed["assignee_candidates"],
                   assignee_name_heard=parsed.get("assignee_name_heard"))
    if parsed.get("due_at"):
        upd["due_at"] = parsed["due_at"]
    d = await state.get_data()
    if not d.get("title") or len((msg.text or "").split()) > 4:
        upd["title"] = parsed["title"]
    await state.update_data(**upd)
    await show_confirm(msg, state, u, lang)


# ============ ovoz / erkin matn -> vazifa ============
@router.message(F.voice | F.audio)
async def voice_task(msg: Message, state: FSMContext, u: dict | None, lang: str, bot: Bot):
    if not u:
        return await msg.answer(t(lang, "not_linked"))
    if not is_manager(u):
        return await msg.answer(t(lang, "voice_no_perm"))
    cur = await state.get_state()
    if cur and cur.startswith("Submit"):
        return
    wait = await msg.answer(t(lang, "voice_processing"))
    buf = await bot.download(msg.voice or msg.audio)
    try:
        parsed = await api.voice_task(u["id"], buf.read(), lang)
    except ApiError as e:
        await wait.delete()
        if e.code == "VOICE_NOT_CONFIGURED":
            return await msg.answer(t(lang, "voice_off"))
        return await err(msg, lang, e)
    await wait.delete()
    await from_parsed(msg, state, u, lang, parsed)


async def from_parsed(msg: Message, state: FSMContext, u: dict, lang: str, parsed: dict):
    await state.clear()
    data = {k: parsed.get(k) for k in ("transcript", "title", "description", "due_at",
                                       "assignee_id", "assignee_name_heard",
                                       "assignee_candidates", "warnings")}
    if data.get("assignee_id"):
        c = next((c for c in parsed.get("assignee_candidates", [])
                  if c["id"] == data["assignee_id"]), None)
        data["assignee_name"] = c["full_name"] if c else None
    await state.set_data(data)
    await show_confirm(msg, state, u, lang)


@router.message(F.text, ~F.text.startswith("/"))
async def free_text(msg: Message, state: FSMContext, u: dict | None, lang: str):
    if not u:
        if re.fullmatch(r"\s*\d{6}\s*", msg.text or ""):
            await state.set_state(Link.code)
            return await link_code(msg, state, lang)
        return await msg.answer(t(lang, "welcome_unlinked"))
    if await state.get_state():
        return
    words = (msg.text or "").split()
    if is_manager(u) and len(words) >= 4:
        wait = await msg.answer(t(lang, "type_text"))
        try:
            parsed = await api.parse_task(u["id"], msg.text, lang)
        except ApiError as e:
            await wait.delete()
            if e.code == "VOICE_NOT_CONFIGURED":
                return await msg.answer(t(lang, "voice_off"))
            return await err(msg, lang, e)
        await wait.delete()
        return await from_parsed(msg, state, u, lang, parsed)
    await menu(msg, u, lang)


# ============ outbox ishchisi ============
async def outbox_worker(bot: Bot):
    """API hali ko'tarilmagan bo'lishi mumkin — bunda jim kutamiz, log to'ldirmaymiz."""
    down = 0
    while True:
        try:
            rows = await api.outbox(limit=40)
            if down:
                log.info("API qaytdi, xabarlar yuborilmoqda")
                down = 0
            sent, failed = [], []
            for n in rows:
                lang = n.get("lang") or "uz"
                try:
                    await bot.send_message(n["telegram_user_id"],
                                           notif_text(lang, n["event"], n.get("payload") or {}),
                                           reply_markup=notif_kb(lang, n["event"],
                                                                 n.get("payload") or {}))
                    sent.append(n["id"])
                except Exception as e:  # noqa: BLE001 - bitta xato navbatni to'xtatmasin
                    log.warning("xabar yuborilmadi %s: %s", n["id"], e)
                    failed.append(n["id"])
            if sent or failed:
                await api.outbox_ack(sent, failed)
        except Exception as e:  # noqa: BLE001
            down += 1
            if down == 1:
                log.warning("API javob bermayapti (%s) — kutyapman", type(e).__name__)
        await asyncio.sleep(settings.OUTBOX_INTERVAL * (5 if down else 1))


TOKEN_HELP = """
========================================================================
BOT TOKENI NOTO'G'RI — Telegram "Unauthorized" javob berdi.

Token eskirgan, bekor qilingan yoki .env ga xato ko'chirilgan.

  1) Telegramda @BotFather ni oching
  2) /mybots -> botingiz -> API Token
     (kerak bo'lsa "Revoke current token" bilan yangisini oling)
  3) .env faylidagi BOT_TOKEN= qatoriga o'sha tokenni qo'ying
     Token ko'rinishi: 1234567890:AAH...  (qo'shtirnoq va bo'sh joysiz)
  4) docker compose up -d --build bot

Diqqat: .env dagi token bilan bot ishlaydi. Boshqa hech narsa o'zgartirilmaydi.
========================================================================"""


CONFLICT_HELP = """
========================================================================
BOSHQA BOT AYNAN SHU TOKEN BILAN ISHLAYAPTI.

Telegram bitta tokenga bitta ulanish beradi. Ikkinchisi ishga tushsa, xabarlar
ikkisi o'rtasida bo'linib ketadi: kod yuborasiz, uni boshqa nusxa ushlab, o'z
bazasidan qidiradi va "Kod noto'g'ri" deydi.

Ko'p uchraydigan sabab: serverda eski nusxa ishlab turibdi, siz esa uni mahalliy
kompyuterda ham ishga tushirgansiz (yoki aksincha).

Yechim (bittasini tanlang):
  1) Ikkinchi nusxani to'xtating:
       serverda -> docker compose -f docker-compose.prod.yml stop bot
       mahalliy -> docker compose stop bot
  2) Yoki sinash uchun @BotFather dan ALOHIDA bot oching va uning tokenini
     mahalliy .env ga qo'ying. Shunda server boti tegilmaydi.

Bot to'xtamaydi - ikkinchi nusxa o'chgach o'zi ishlab ketadi.
========================================================================"""


async def warn_if_conflict(bot: Bot):
    """Ishga tushishda bir marta tekshiramiz: shu token bilan boshqa nusxa ishlayaptimi.

    Aks holda aiogram har bir necha soniyada bir xil ERROR yozadi va sabab ko'rinmaydi -
    aslida muammo kodda emas, ikkinchi nusxada.
    """
    try:
        await bot.get_updates(offset=-1, limit=1, timeout=0)
    except TelegramConflictError:
        log.error("%s", CONFLICT_HELP)
    except Exception:  # noqa: BLE001 - tekshiruv ishga tushishga to'sqinlik qilmasin
        pass


async def main():
    if not settings.BOT_TOKEN or ":" not in settings.BOT_TOKEN:
        log.error("BOT_TOKEN .env da yo'q yoki noto'g'ri ko'rinishda.%s", TOKEN_HELP)
        raise SystemExit(1)
    bot = Bot(settings.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.message.middleware(UserMiddleware())
    dp.callback_query.middleware(UserMiddleware())
    dp.include_router(router)

    # Tokenni birinchi bo'lib tekshiramiz: noto'g'ri bo'lsa uzun traceback o'rniga
    # nima qilish kerakligi yoziladi.
    try:
        me = await bot.get_me()
    except TelegramUnauthorizedError:
        log.error("%s", TOKEN_HELP)
        await bot.session.close()
        raise SystemExit(1)
    except Exception as e:  # noqa: BLE001 - tarmoq muammosi: qayta urinib ko'rish mumkin
        log.error("Telegramga ulanib bo'lmadi: %s", e)
        await bot.session.close()
        raise SystemExit(1)

    log.info("bot: @%s (%s)", me.username, me.full_name)
    try:
        if me.username:
            await api.register_username(me.username)
    except Exception as e:  # noqa: BLE001 - API keyinroq ko'tariladi, bot ishlayveradi
        log.warning("username API ga yozilmadi (%s) — keyin qayta yoziladi", type(e).__name__)

    await bot.delete_webhook(drop_pending_updates=False)
    await warn_if_conflict(bot)
    asyncio.create_task(outbox_worker(bot))
    log.info("bot ishga tushdi")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
