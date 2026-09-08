"""Bot-side checks: i18n completeness, message/keyboard rendering, and a live end-to-end
run of every API call the bot makes (against a real API started by conftest)."""
import asyncio
import os
import sys
from datetime import date, timedelta

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from i18n import T, t, status_label, prio_label, block_label, STATUS_ICON  # noqa: E402
import render  # noqa: E402

D = lambda n: (date.today() + timedelta(days=n)).isoformat()

SAMPLE = {
    "id": 7, "code": "V-1027", "title": "Monolit plita — 8-qavat betonlash", "status": "progress",
    "priority": "high", "assignee_name": "Rustam Ergashev", "reviewer_name": "Doniyor Toshmatov",
    "planned_start": D(-2), "planned_end": D(1), "overdue_days": 0, "review_days": 0, "blocked_days": 0,
    "checklist_done": 5, "checklist_total": 8, "photos_count": 9, "progress_percent": 62,
    "return_count": 2, "dependency_pending": ["V-1019"], "blocked_reason": None, "blocked_note": None,
    "location_path": [{"name": "B blok"}, {"name": "8-qavat"}], "project_name": "TXT-07",
    "permissions": {"start": False, "submit_review": True, "accept": False, "return": False,
                    "block": True, "unblock": False, "progress": True, "checklist": True, "comment": True},
    "checklist": [{"id": 1, "title": "Qolip", "is_required": True, "is_done": True},
                  {"id": 2, "title": "Armatura", "is_required": True, "is_done": False}],
}


# ---------------------------------------------------------------- i18n
def test_all_languages_have_every_key():
    base = set(T["uz"])
    for lang in ("ru", "en"):
        missing = base - set(T[lang])
        assert not missing, f"{lang} misses: {sorted(missing)}"
        extra = set(T[lang]) - base
        assert not extra, f"{lang} has unknown keys: {sorted(extra)}"


def test_placeholders_match_across_languages():
    import re
    ph = lambda s: set(re.findall(r"\{(\w+)\}", s)) if isinstance(s, str) else set()
    for key, uzv in T["uz"].items():
        for lang in ("ru", "en"):
            assert ph(uzv) == ph(T[lang][key]), f"{lang}/{key}: placeholders differ"


def test_labels_for_every_status_priority_reason():
    from i18n import STATUS, PRIO, BLOCK
    for lang in ("uz", "ru", "en"):
        for s in ("plan", "progress", "review", "done", "blocked", "cancelled"):
            assert status_label(lang, s) and STATUS_ICON[s]
        for p in ("low", "normal", "high"):
            assert prio_label(lang, p)
        for b in ("material_yoq", "hujjat_kutilmoqda", "texnika_band", "ishchi_yetmadi",
                  "oldingi_ish", "obhavo", "qaror_kutilmoqda", "boshqa"):
            assert block_label(lang, b) != b


def test_notification_templates_render_in_all_languages():
    from main import render_notification
    events = ["assigned", "due_tomorrow", "due_today", "overdue", "overdue_3", "submitted_review",
              "returned", "blocked", "blocked_24h", "accepted", "reopened", "cancelled",
              "review_aging", "mentioned", "comment", "dates_changed", "assigned_reviewer"]
    payload = {"code": "V-1027", "title": "Test", "planned_end": D(1), "assigned_by": "Rahbar",
               "days": 3, "reason": "material_yoq", "note": "izoh", "by": "A", "text": "salom"}
    for lang in ("uz", "ru", "en"):
        for ev in events:
            out = render_notification(lang, ev, payload)
            assert out and "{" not in out, f"{lang}/{ev}: {out}"
            assert "V-1027" in out


def test_digest_renders():
    from main import render_notification
    p = {"today": [{"code": "V-1", "title": "A"}], "overdue": [{"code": "V-2", "title": "B", "days": 3}],
         "blocked": [{"code": "V-3", "title": "C", "reason": "material_yoq"}],
         "review": [{"code": "V-4", "title": "D"}],
         "urgent": [{"code": "V-5", "title": "E", "planned_end": D(0)}],
         "queue_count": 2, "queue_oldest_days": 4,
         "counts": {"today": 1, "overdue": 1, "blocked": 1, "review": 1}}
    for lang in ("uz", "ru", "en"):
        out = render_notification(lang, "digest", p)
        assert "V-1" in out and "V-5" in out and "{" not in out


# ---------------------------------------------------------------- rendering
def test_task_card_and_keyboard():
    for lang in ("uz", "ru", "en"):
        card = render.task_card(lang, SAMPLE)
        assert "V-1027" in card and "Rustam Ergashev" in card
        assert "B blok · 8-qavat" in card
        assert "V-1019" in card          # pending dependency shown
        assert "{" not in card
        kb = render.task_kb(lang, SAMPLE)
        texts = [b.text for row in kb.inline_keyboard for b in row]
        datas = [b.callback_data for row in kb.inline_keyboard for b in row if b.callback_data]
        assert any("t:review:7" == d for d in datas)
        assert not any(d.startswith("t:accept") for d in datas)   # permissions respected
        assert any(d.startswith("t:block") for d in datas)


def test_blocked_card_shows_reason():
    tk = {**SAMPLE, "status": "blocked", "blocked_reason": "material_yoq", "blocked_note": "Sement yo'q",
          "permissions": {"unblock": True}}
    card = render.task_card("uz", tk)
    assert "Material yo'q" in card and "Sement yo'q" in card
    datas = [b.callback_data for row in render.task_kb("uz", tk).inline_keyboard for b in row]
    assert any(d.startswith("t:unblock") for d in datas)


def test_checklist_keyboard_toggles():
    kb = render.checklist_kb("uz", SAMPLE)
    datas = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert "ck:7:1:0" in datas   # done -> undone
    assert "ck:7:2:1" in datas   # undone -> done


def test_confirm_card_flags_missing_pieces():
    d = {"transcript": "Rustam Ergashevga oktabrgacha 1-bosqichni tugatsin", "title": "1-bosqichni tugatish",
         "priority": "high", "planned_start": D(0), "planned_end": D(30), "project_id": None,
         "assignee_id": None, "assignee_candidates": [{"id": 4, "full_name": "Rustam Ergashev", "score": 92, "role": "Bajaruvchi"}],
         "assignee_name_heard": "Rustam Erkashev", "warnings": []}
    for lang in ("uz", "ru", "en"):
        txt = render.confirm_card(lang, d, {})
        assert "1-bosqichni tugatish" in txt and "🎙" in txt
        assert "{" not in txt
    kb = render.confirm_kb("uz", d)
    datas = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert "nt:pick_a:4" in datas
    assert "nt:send" not in datas          # cannot send while assignee/project unknown
    d2 = {**d, "assignee_id": 4, "project_id": 1, "type_id": 1, "assignee_candidates": []}
    datas2 = [b.callback_data for row in render.confirm_kb("uz", d2).inline_keyboard for b in row]
    assert "nt:send" in datas2


def test_menu_depends_on_permissions():
    boss = {b.text for row in render.main_menu("uz", {"tasks.create", "tasks.accept"}).keyboard for b in row}
    worker = {b.text for row in render.main_menu("uz", {"tasks.start"}).keyboard for b in row}
    assert t("uz", "btn_new") in boss and t("uz", "btn_review") in boss
    assert t("uz", "btn_new") not in worker
    assert t("uz", "btn_my") in worker


def test_pagination_keyboard():
    items = [{"id": i, "name": f"User {i}"} for i in range(20)]
    kb = render.list_kb(items, "nta", page=0, per=8)
    datas = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert "nta:0" in datas and "nta_pg:1" in datas and "nta:9" not in datas
    kb2 = render.list_kb(items, "nta", page=1, per=8)
    d2 = [b.callback_data for row in kb2.inline_keyboard for b in row]
    assert "nta_pg:0" in d2 and "nta_pg:2" in d2


@pytest.mark.asyncio
async def test_pagination_handlers_are_wired_for_every_picker():
    """list_kb() 8 tadan ko'p element bo'lsa "keyingi sahifa" tugmasini chiqaradi, lekin loyiha
    (Yangi vazifa) va vazifa tanlash (Kunlik hisobot / Muammo) ro'yxatlari uchun bu tugmani ushlaydigan
    handler umuman yo'q edi - superadmin 8 tadan ko'p loyihaga ega bo'lganda (demo bazada 12 ta)
    yoki bir xodimda 8 tadan ko'p vazifa bo'lganda tugma hech narsa qilmas edi."""
    import main as bot
    from aiogram.fsm.context import FSMContext
    from aiogram.fsm.storage.base import StorageKey
    from aiogram.fsm.storage.memory import MemoryStorage

    class Sink:
        def __init__(self):
            self.markups = []

        async def edit_reply_markup(self, reply_markup=None, **kw):
            self.markups.append(reply_markup)

    class Cb:
        def __init__(self, data, message):
            self.data = data
            self.message = message
            self.alerts: list[str] = []

        async def answer(self, text="", show_alert=False):
            if text:
                self.alerts.append(text)

    storage = MemoryStorage()
    st = FSMContext(storage=storage, key=StorageKey(bot_id=1, chat_id=1, user_id=1))
    items = [{"id": i, "name": f"Item {i}"} for i in range(12)]
    for state_key, prefix, handler in (
        ("_projects", "ntp", bot.ntp_page),
        ("_rep_items", "rep", bot.rep_page),
        ("_blk_items", "blkt", bot.blkt_page),
    ):
        await st.update_data(**{state_key: items})
        sink = Sink()
        cb = Cb(f"{prefix}_pg:1", sink)
        await handler(cb, st, "uz")
        assert not cb.alerts
        assert sink.markups, f"{prefix}_pg: handler ro'yxatdan o'tmagan yoki javob bermadi"
        datas = [b.callback_data for row in sink.markups[0].inline_keyboard for b in row]
        assert f"{prefix}:8" in datas, f"{prefix} ikkinchi sahifasi noto'g'ri chiqdi"
        assert f"{prefix}_pg:0" in datas, "orqaga qaytish tugmasi yo'q"


def test_date_parser():
    from main import parse_date
    assert parse_date("25.10.2026") == date(2026, 10, 25)
    y = date.today().year
    assert parse_date("25.10") in (date(y, 10, 25), date(y + 1, 10, 25))
    assert parse_date("2026-10-25") == date(2026, 10, 25)
    assert parse_date("salom") is None


def test_quiet_hours_helper():
    from main import _quiet_hours
    assert isinstance(_quiet_hours(), bool)


# ---------------------------------------------------------------- live API flow
PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
       b"\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82")


@pytest.mark.asyncio
async def test_bot_api_client_full_flow(live_api):
    """Every call bot/api.py makes, against a real server."""
    from api import api, ApiError
    import httpx

    base, admin_tok = live_api
    api.c = httpx.AsyncClient(base_url=base, timeout=30)

    # --- admin (id 1) sets up a project/users through the same client ---
    me = await api.me(1)
    assert me["user"]["login"] == "admin"

    projects = await api.projects(1)
    assert projects and projects[0]["id"]
    pid = projects[0]["id"]
    locs = await api.locations(1, pid)
    assert locs
    types = await api.task_types(1)
    assert types
    users = await api.users(1)
    boss = next(u for u in users if u["login"] == "admin")
    worker = next(u for u in users if u["login"] == "ishchi")

    # --- linking ---
    assert await api.user_by_tg(424242) is None
    async with httpx.AsyncClient(base_url=base, timeout=30) as c:
        r = await c.post("/telegram/link-code", headers={"Authorization": f"Bearer {admin_tok}"})
        code = r.json()["code"]
    linked = await api.consume_code(code, 424242)
    assert linked["telegram_user_id"] == 424242
    assert (await api.user_by_tg(424242))["login"] == "admin"

    # --- create through the bot path ---
    tk = await api.create_task(boss["id"], {
        "project_id": pid, "location_id": locs[0]["id"], "type_id": types[-1]["id"],
        "title": "Bot orqali berilgan vazifa", "priority": "high",
        "assignee_id": worker["id"], "reviewer_id": boss["id"],
        "planned_start": D(0), "planned_end": D(2)})
    assert tk["code"].startswith("V-")
    tid = tk["id"]

    assert (await api.task(boss["id"], tid))["title"] == tk["title"]
    assert (await api.task_by_code(boss["id"], tk["code"]))["id"] == tid

    lst = await api.tasks(worker["id"], mine=True, status="plan,progress", limit=50)
    assert any(x["id"] == tid for x in lst["items"])

    # --- worker runs the task from the bot ---
    assert (await api.start(worker["id"], tid))["status"] == "progress"
    det = await api.task(worker["id"], tid)
    req = [c["id"] for c in det["checklist"] if c["is_required"]]
    if req:
        upd = await api.checklist_set(worker["id"], tid, [{"id": i, "is_done": True} for i in req])
        assert upd["checklist_done"] == len(req)
    row = await api.daily(worker["id"], tid, {"date": D(0), "quantity": 12, "workers_count": 4, "note": "botdan"})
    assert row["source"] == "bot"
    for kind in det["required_evidence_kinds"]:
        att = await api.upload(worker["id"], tid, PNG, "photo.jpg", "image/jpeg", kind, row["id"])
        assert att["source"] == "bot"

    await api.comment(worker["id"], tid, "Bot orqali izoh")
    assert (await api.submit_review(worker["id"], tid))["status"] == "review"

    # --- reviewer returns, then accepts ---
    assert (await api.return_task(boss["id"], tid, "Foto aniq emas"))["return_count"] == 1
    assert (await api.submit_review(worker["id"], tid))["status"] == "review"
    assert (await api.accept(boss["id"], tid))["status"] == "done"

    # --- block / unblock ---
    tk2 = await api.create_task(boss["id"], {
        "project_id": pid, "type_id": types[-1]["id"], "title": "Bloklanadigan vazifa",
        "assignee_id": worker["id"], "reviewer_id": boss["id"], "planned_start": D(0), "planned_end": D(2)})
    await api.start(worker["id"], tk2["id"])
    b = await api.block(worker["id"], tk2["id"], "material_yoq", "Sement yetkazilmadi")
    assert b["status"] == "blocked" and b["blocked_reason"] == "material_yoq"
    assert (await api.unblock(worker["id"], tk2["id"]))["status"] == "progress"

    # --- outbox: the worker is not linked, the admin is -> admin gets telegram rows ---
    out = await api.outbox()
    assert isinstance(out, list)
    if out:
        await api.outbox_ack([out[0]["id"]], [])

    # --- language switch + meta ---
    assert (await api.set_lang(boss["id"], "ru"))["lang"] == "ru"
    await api.set_lang(boss["id"], "uz")
    assert "block_reasons" in await api.meta(boss["id"])

    # --- voice endpoints report "not configured" rather than crashing ---
    with pytest.raises(ApiError) as e:
        await api.parse_task(boss["id"], "Rustamga ertaga devor terish", "uz", pid)
    assert e.value.code == "VOICE_NOT_CONFIGURED"

    await api.c.aclose()


@pytest.mark.asyncio
async def test_bot_api_error_mapping(live_api):
    from api import api, ApiError
    import httpx
    base, _ = live_api
    api.c = httpx.AsyncClient(base_url=base, timeout=30)
    with pytest.raises(ApiError) as e:
        await api.task(1, 99999)
    assert e.value.status == 404 and e.value.code == "TASK_NOT_FOUND"
    with pytest.raises(ApiError) as e:
        await api.task_by_code(1, "V-999999")
    assert e.value.status == 404
    await api.c.aclose()


# ---------------------------------------------------------------- role-aware bot
ROLE_PERMS = {
    "admin": {"tasks.read", "tasks.create", "tasks.start", "tasks.submit_review", "tasks.accept", "tasks.return",
              "tasks.block", "progress.create", "reports.read", "admin.users", "tasks.export"},
    "rahbar": {"tasks.read", "tasks.create", "tasks.start", "tasks.submit_review", "tasks.accept", "tasks.return",
               "tasks.block", "progress.create", "reports.read", "tasks.export"},
    "prorab": {"tasks.read", "tasks.create", "tasks.start", "tasks.submit_review", "tasks.block",
               "progress.create", "reports.read", "tasks.export"},
    "bajaruvchi": {"tasks.read", "tasks.start", "tasks.submit_review", "tasks.block", "progress.create",
                   "checklist.edit", "attachments.upload", "comments.create"},
    "tekshiruvchi": {"tasks.read", "tasks.accept", "tasks.return", "reports.read", "tasks.export", "comments.create"},
    "kuzatuvchi": {"tasks.read", "reports.read"},
}


def _menu(role, lang="uz"):
    kb = render.main_menu(lang, ROLE_PERMS[role], role)
    return {b.text for row in kb.keyboard for b in row}


def test_menu_is_different_for_every_role():
    m = {r: _menu(r) for r in ROLE_PERMS}
    # superadmin: kuzatadi va vazifa beradi, lekin o'zi hech qachon ijrochi/tekshiruvchi
    # bo'lmagani uchun "o'z vazifang" tugmalari (doim bo'sh chiqadigan) ko'rsatilmaydi
    for key in ("btn_new", "btn_overdue", "btn_blocked", "btn_reports", "btn_team", "btn_search"):
        assert t("uz", key) in m["admin"], key
    for key in ("btn_my", "btn_report", "btn_review", "btn_problem"):
        assert t("uz", key) not in m["admin"], key
    # rahbar - jamoadan tashqari hammasi
    assert t("uz", "btn_team") not in m["rahbar"]
    assert {t("uz", "btn_new"), t("uz", "btn_reports"), t("uz", "btn_review")} <= m["rahbar"]
    # prorab - vazifa beradi, hisobot ko'radi, lekin qabul qilmaydi va jamoani boshqarmaydi
    assert t("uz", "btn_new") in m["prorab"] and t("uz", "btn_reports") in m["prorab"]
    assert t("uz", "btn_review") not in m["prorab"] and t("uz", "btn_team") not in m["prorab"]
    # ishchi - faqat o'z ishi
    assert {t("uz", "btn_my"), t("uz", "btn_report"), t("uz", "btn_problem")} <= m["bajaruvchi"]
    for key in ("btn_new", "btn_review", "btn_reports", "btn_overdue", "btn_blocked", "btn_team"):
        assert t("uz", key) not in m["bajaruvchi"], key
    # tekshiruvchi - qabul qiladi, hisobot ko'radi, lekin hisobot topshirmaydi
    assert t("uz", "btn_review") in m["tekshiruvchi"]
    assert t("uz", "btn_report") not in m["tekshiruvchi"] and t("uz", "btn_new") not in m["tekshiruvchi"]
    # kuzatuvchi - faqat ko'radi. "Vazifalarim" ham yo'q: unga hech qachon vazifa biriktirilmaydi
    # va tekshiruvchi qilib ham tayinlanmaydi, ya'ni bu ro'yxat doim bo'sh chiqar edi
    assert m["kuzatuvchi"] == {t("uz", k) for k in ("btn_overdue", "btn_blocked", "btn_reports",
                                                    "btn_search", "btn_lang", "btn_help")}
    # har rol o'z to'plamiga ega
    assert len({frozenset(v) for v in m.values()}) == len(m)


def test_menu_rows_are_pairs_and_translated():
    for lang in ("uz", "ru", "en"):
        for role in ROLE_PERMS:
            kb = render.main_menu(lang, ROLE_PERMS[role])
            assert all(len(row) <= 2 for row in kb.keyboard)
            texts = [b.text for row in kb.keyboard for b in row]
            assert len(texts) == len(set(texts))
            assert all(txt.strip() for txt in texts)


def test_daily_report_notification_renders():
    from main import render_notification
    p = {"code": "V-1042", "title": "Beton ishlari — B blok 8-qavat", "by": "Rustam Ergashev",
         "date": "2026-09-07", "quantity": 42.0, "unit": "m3", "workers": 9,
         "note": "Yomg'ir tufayli sekinlashdi", "total": 156.0, "plan": 240.0, "duplicate": False}
    for lang in ("uz", "ru", "en"):
        out = render_notification(lang, "daily_report", p)
        assert "V-1042" in out and "Rustam Ergashev" in out
        assert "42" in out and "m3" in out and "9" in out
        assert "156" in out and "240" in out
        assert "{" not in out and "42.0" not in out       # raqamlar toza ko'rinadi
    dup = render_notification("uz", "daily_report", {**p, "duplicate": True, "note": ""})
    assert "⚠️" in dup


def test_number_formatting():
    from main import _num
    assert _num(12.0) == "12" and _num(12.5) == "12.5" and _num(0) == "0"
    assert _num(None) == "None" or _num(None) == "none"


@pytest.mark.asyncio
async def test_manager_summary_endpoint_used_by_bot(live_api):
    from api import api
    import httpx
    base, _ = live_api
    api.c = httpx.AsyncClient(base_url=base, timeout=30)
    s = await api.summary(1)
    assert "kpi" in s and "blocked_reasons" in s and "staff" in s
    assert set(s["kpi"]) >= {"open", "overdue", "blocked", "review", "review_oldest_days", "on_time_pct", "return_pct", "total"}
    await api.c.aclose()
