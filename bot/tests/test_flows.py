"""Botning haqiqiy handlerlarini soxta Telegram xabarlari bilan, jonli API ustida ishlatib tekshirish.
Har rol o'z oqimini bosib o'tadi: ishchi ish boshlaydi -> hisobot topshiradi -> muammo qo'yadi,
rahbar vazifa beradi va KPI ko'radi, tekshiruvchi qabul qiladi."""
from __future__ import annotations

import os
import sys
from datetime import date, timedelta

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

import main as bot
import render
from i18n import t

D = lambda n: (date.today() + timedelta(days=n)).isoformat()
PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
       b"\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82")


class Sent:
    """msg.answer(...) natijalari."""
    def __init__(self):
        self.texts: list[str] = []
        self.markups: list = []

    @property
    def last(self): return self.texts[-1] if self.texts else ""

    def buttons(self):
        out = []
        for m in self.markups:
            for row in getattr(m, "inline_keyboard", []) or []:
                out += [b.callback_data for b in row if b.callback_data]
        return out

    def keys(self):
        out = []
        for m in self.markups:
            for row in getattr(m, "keyboard", []) or []:
                out += [b.text for b in row]
        return out


class FakeUser:
    def __init__(self, tg_id):
        self.id = tg_id
        self.language_code = "uz"


class FakeMsg:
    def __init__(self, sink: Sent, tg_id=1, text=None, photo=None):
        self.sink = sink
        self.from_user = FakeUser(tg_id)
        self.text = text
        self.caption = None
        self.photo = photo
        self.document = None
        self.voice = None
        self.audio = None

    async def answer(self, text, reply_markup=None, **kw):
        self.sink.texts.append(text)
        self.sink.markups.append(reply_markup)
        return self

    async def edit_text(self, text, reply_markup=None, **kw):
        self.sink.texts.append(text)
        self.sink.markups.append(reply_markup)
        return self

    async def edit_reply_markup(self, reply_markup=None, **kw):
        self.sink.markups.append(reply_markup)
        return self

    async def delete(self):
        return True


class FakeCb:
    def __init__(self, sink: Sent, data, tg_id=1):
        self.data = data
        self.from_user = FakeUser(tg_id)
        self.message = FakeMsg(sink, tg_id)
        self.sink = sink
        self.alerts: list[str] = []

    async def answer(self, text="", show_alert=False):
        if text:
            self.alerts.append(text)


def ctx_factory():
    storage = MemoryStorage()

    def make(tg_id=1):
        return FSMContext(storage=storage, key=StorageKey(bot_id=1, chat_id=tg_id, user_id=tg_id))
    return make


@pytest.fixture
def sink():
    return Sent()


@pytest.fixture(autouse=True)
async def fresh_api(live_api):
    """Har test o'z event loop'ida ishlaydi - HTTP klientni har safar yangilaymiz.
    Handlerlar `isinstance(x, CallbackQuery)` bilan ishlaydi, shuning uchun soxta klassni ham
    shu tekshiruvga qo'shamiz - handler kodi o'zgarmaydi."""
    import httpx
    from aiogram.types import CallbackQuery as RealCallbackQuery
    from api import api
    base, _ = live_api
    api.c = httpx.AsyncClient(base_url=base, timeout=30)
    bot.CallbackQuery = (RealCallbackQuery, FakeCb)
    bot.UserMiddleware.cache.clear()
    yield
    bot.CallbackQuery = RealCallbackQuery
    await api.c.aclose()


@pytest.fixture(scope="session")
def world(live_api):
    """Jonli API ustida rollar to'plami: admin, rahbar, prorab, ishchi, tekshiruvchi, kuzatuvchi."""
    import httpx
    base, tok = live_api
    h = {"Authorization": f"Bearer {tok}"}
    with httpx.Client(base_url=base, timeout=20) as c:
        roles = {r["code"]: r["id"] for r in c.get("/roles", headers=h).json()}
        pr = c.get("/projects", headers=h).json()[0]
        locs = c.get("/locations", headers=h, params={"project_id": pr["id"]}).json()
        block = next(l for l in locs if l["kind"] == "block")
        floor = next(l for l in locs if l["kind"] == "floor")
        made = {}
        for login, name, role, st, sid in [
            ("f_rahbar", "Rahbar Test", "rahbar", "project", pr["id"]),
            ("f_prorab", "Prorab Test", "prorab", "location", block["id"]),
            ("f_ishchi", "Ishchi Test", "bajaruvchi", "system", None),
            ("f_qc", "Tekshiruvchi Test", "tekshiruvchi", "project", pr["id"]),
            ("f_kuzat", "Kuzatuvchi Test", "kuzatuvchi", "project", pr["id"]),
        ]:
            r = c.post("/users", json={"full_name": name, "login": login, "password": "1234",
                                       "role_id": roles[role], "scope_type": st, "scope_id": sid}, headers=h)
            made[login] = r.json() if r.status_code == 201 else c.get("/users", headers=h,
                                                                      params={"q": login}).json()[0]
        types = c.get("/task-types", headers=h).json()
        umumiy = next(t_ for t_ in types if t_["name"] == "Umumiy vazifa")
        # har rolni alohida telegram id ga bog'laymiz
        tg = {}
        for i, (login, u) in enumerate(made.items(), start=1):
            tok_u = c.post("/auth/login", json={"login": login, "password": "1234"}).json()["access_token"]
            code = c.post("/telegram/link-code", headers={"Authorization": f"Bearer {tok_u}"}).json()["code"]
            tg_id = 900000 + i
            c.post("/telegram/consume-code", json={"code": code, "telegram_user_id": tg_id},
                   headers={"X-Service-Token": os.environ["SERVICE_TOKEN"]})
            tg[login] = tg_id
    return {"users": made, "tg": tg, "project": pr, "block": block, "floor": floor, "type": umumiy}


async def resolve(tg_id):
    """UserMiddleware kabi foydalanuvchini API dan oladi."""
    from api import api
    bot.UserMiddleware.invalidate(tg_id)
    return await api.user_by_tg(tg_id)


# ---------------------------------------------------------------- menyu
@pytest.mark.asyncio
async def test_every_role_gets_its_own_menu(world, sink):
    seen = {}
    for login in world["tg"]:
        u = await resolve(world["tg"][login])
        s = Sent()
        await bot.start(FakeMsg(s, world["tg"][login]), ctx_factory()(), u, "uz")
        seen[login] = set(s.keys())
        assert seen[login], login
    # "Vazifalarim" - faqat vazifa biriktiriladigan yoki tekshiradigan odamlarda
    for login in ("f_rahbar", "f_prorab", "f_ishchi", "f_qc"):
        assert t("uz", "btn_my") in seen[login], login
    assert t("uz", "btn_my") not in seen["f_kuzat"]   # kuzatuvchida doim bo'sh chiqar edi
    assert t("uz", "btn_new") in seen["f_rahbar"] and t("uz", "btn_reports") in seen["f_rahbar"]
    assert t("uz", "btn_new") in seen["f_prorab"]
    assert t("uz", "btn_new") not in seen["f_ishchi"] and t("uz", "btn_report") in seen["f_ishchi"]
    assert t("uz", "btn_review") in seen["f_qc"] and t("uz", "btn_report") not in seen["f_qc"]
    assert t("uz", "btn_report") not in seen["f_kuzat"] and t("uz", "btn_reports") in seen["f_kuzat"]


# ---------------------------------------------------------------- rahbar vazifa beradi (tugmalar bilan)
@pytest.mark.asyncio
async def test_manager_creates_task_with_buttons(world):
    from api import api
    mk = ctx_factory()
    tg = world["tg"]["f_rahbar"]
    u = await resolve(tg)
    st = mk(tg)
    s = Sent()

    await bot.new_task(FakeMsg(s, tg), st, u, "uz")
    # loyiha yoki bajaruvchi tanlash chiqadi
    assert s.buttons(), "yaratish sehrgari boshlanmadi"
    if any(b.startswith("ntp:") for b in s.buttons()):
        cb = FakeCb(s, f"ntp:{world['project']['id']}", tg)
        await bot.nt_project(cb, st, u, "uz")
    data = await st.get_data()
    assert data.get("project_id")

    # bajaruvchini tanlaymiz
    s2 = Sent()
    await bot.ask_assignee(FakeMsg(s2, tg), st, u, "uz")
    picks = [b for b in s2.buttons() if b.startswith("nta:")]
    assert picks, "bajaruvchilar ro'yxati chiqmadi"
    worker_id = world["users"]["f_ishchi"]["id"]
    target = f"nta:{worker_id}" if f"nta:{worker_id}" in picks else picks[0]
    cb = FakeCb(s2, target, tg)
    await bot.nt_assignee(cb, st, u, "uz")

    # sarlavha -> muddat -> muhimlik -> tasdiq
    await bot.nt_title(FakeMsg(Sent(), tg, text="Botdan berilgan vazifa"), st, u, "uz")
    s3 = Sent()
    await bot.nt_deadline(FakeCb(s3, "nt:dl:3", tg), st, u, "uz")
    s4 = Sent()
    await bot.nt_prio(FakeCb(s4, "nt:prio:high", tg), st, u, "uz")
    card = s4.texts[-1] if s4.texts else ""
    assert "Botdan berilgan vazifa" in card
    assert "nt:send" in s4.buttons(), f"Yuborish tugmasi yo'q: {s4.buttons()}"

    s5 = Sent()
    cb = FakeCb(s5, "nt:send", tg)
    await bot.nt_send(cb, st, u, "uz")
    assert any("✅" in x for x in s5.texts), s5.texts
    created = [x for x in s5.texts if "V-" in x]
    assert created
    code = [w for w in created[0].replace("<b>", " ").replace("</b>", " ").split() if w.startswith("V-")][0]
    tk = await api.task_by_code(u["id"], code)
    assert tk["assignee_id"] == worker_id and tk["priority"] == "high"
    assert tk["planned_end"] == D(3)
    # tekshiruvchi avtomatik loyihaning tekshiruvchisi bo'ladi, vazifani bergan odam emas
    assert tk["reviewer_id"] == world["users"]["f_qc"]["id"], "tekshiruvchi noto'g'ri tanlandi"
    assert "Tekshiradi" in card and world["users"]["f_qc"]["full_name"] in card
    world["created"] = tk


# ---------------------------------------------------------------- ishchi: ko'radi, boshlaydi, hisobot beradi
@pytest.mark.asyncio
async def test_worker_sees_starts_and_reports(world):
    from api import api
    mk = ctx_factory()
    tg = world["tg"]["f_ishchi"]
    u = await resolve(tg)
    tk = world["created"]

    s = Sent()
    await bot.my_tasks(FakeMsg(s, tg), u, "uz")
    assert f"t:show:{tk['id']}" in s.buttons(), "yangi vazifa ishchining ro'yxatida yo'q"

    # kartochka ochiladi, "Boshlash" tugmasi bor
    s2 = Sent()
    cb = FakeCb(s2, f"t:show:{tk['id']}", tg)
    await bot.task_action(cb, mk(tg), u, "uz")
    assert f"t:start:{tk['id']}" in s2.buttons()

    s3 = Sent()
    cb = FakeCb(s3, f"t:start:{tk['id']}", tg)
    await bot.task_action(cb, mk(tg), u, "uz")
    assert (await api.task(u["id"], tk["id"]))["status"] == "progress"

    # kunlik hisobot: hajm -> ishchi soni -> foto -> tayyor
    st = mk(tg)
    s4 = Sent()
    await bot.report_cmd(FakeMsg(s4, tg), st, u, "uz")
    if any(b.startswith("rep:") for b in s4.buttons()):
        await bot.report_pick(FakeCb(s4, f"rep:{tk['id']}", tg), st, u, "uz")
    assert (await st.get_state() or "").startswith("Report")

    await bot.report_qty(FakeMsg(Sent(), tg, text="18"), st, "uz")
    await bot.report_workers(FakeMsg(Sent(), tg, text="6"), st, u, "uz")
    s5 = Sent()
    await bot.report_done(FakeMsg(s5, tg, text=t("uz", "btn_done")), st, u, "uz")
    assert "18" in s5.last and "6" in s5.last

    rows = await api._req("GET", f"/tasks/{tk['id']}/daily-progress", u["id"])
    assert rows and float(rows[0]["quantity"]) == 18 and rows[0]["workers_count"] == 6
    assert rows[0]["source"] == "bot"


# ---------------------------------------------------------------- hisobot rahbar/prorab/adminga yetib boradi
@pytest.mark.asyncio
async def test_daily_report_reaches_managers_via_bot_outbox(world):
    from api import api
    out = await api.outbox()
    reports = [o for o in out if o["event"] == "daily_report" and o["task_id"] == world["created"]["id"]]
    assert reports, "kunlik hisobot bo'yicha telegram xabari navbatga tushmadi"
    got = {o["telegram_user_id"] for o in reports}
    assert world["tg"]["f_rahbar"] in got, "rahbar hisobotni olmadi"
    assert world["tg"]["f_prorab"] in got, "prorab hisobotni olmadi"
    assert world["tg"]["f_qc"] in got, "tekshiruvchi hisobotni olmadi"
    assert world["tg"]["f_ishchi"] not in got, "hisobotni yozgan ishchining o'ziga xabar ketdi"
    # matn 3 tilda ham to'g'ri chiqadi
    for lang in ("uz", "ru", "en"):
        txt = bot.render_notification(lang, "daily_report", reports[0]["payload"])
        assert "18" in txt and "{" not in txt
    await api.outbox_ack([o["id"] for o in out], [])


# ---------------------------------------------------------------- ishchi muammo qo'yadi
@pytest.mark.asyncio
async def test_worker_blocks_task(world):
    from api import api
    mk = ctx_factory()
    tg = world["tg"]["f_ishchi"]
    u = await resolve(tg)
    tid = world["created"]["id"]
    st = mk(tg)
    s = Sent()
    await bot.problem_cmd(FakeMsg(s, tg), st, u, "uz")
    if any(b.startswith("blkt:") for b in s.buttons()):
        await bot.block_pick(FakeCb(s, f"blkt:{tid}", tg), st, "uz")
    s2 = Sent()
    await bot.block_reason(FakeCb(s2, f"blk:{tid}:material_yoq", tg), st, "uz")
    await bot.block_note(FakeMsg(Sent(), tg, text="Sement kelmadi"), st, u, "uz")
    tk = await api.task(u["id"], tid)
    assert tk["status"] == "blocked" and tk["blocked_reason"] == "material_yoq"
    assert tk["blocked_note"] == "Sement kelmadi"
    # rahbar/prorab bu haqda xabar oladi
    out = await api.outbox()
    blocked = [o for o in out if o["event"] == "blocked" and o["task_id"] == tid]
    assert {world["tg"]["f_rahbar"], world["tg"]["f_prorab"]} <= {o["telegram_user_id"] for o in blocked}
    await api.outbox_ack([o["id"] for o in out], [])


# ---------------------------------------------------------------- tekshiruvchi qabul qiladi
@pytest.mark.asyncio
async def test_reviewer_queue_and_accept(world):
    from api import api
    mk = ctx_factory()
    tid = world["created"]["id"]
    worker = await resolve(world["tg"]["f_ishchi"])
    await api.unblock(worker["id"], tid)
    det = await api.task(worker["id"], tid)
    req = [c["id"] for c in det["checklist"] if c["is_required"]]
    if req:
        await api.checklist_set(worker["id"], tid, [{"id": i, "is_done": True} for i in req])
    for kind in det["required_evidence_kinds"]:
        await api.upload(worker["id"], tid, PNG, f"{kind}.png", "image/png", kind)
    await api.submit_review(worker["id"], tid)

    tg = world["tg"]["f_qc"]
    qc = await resolve(tg)
    s = Sent()
    await bot.review_queue(FakeMsg(s, tg), qc, "uz")
    assert f"t:show:{tid}" in s.buttons(), "vazifa tekshiruv navbatida ko'rinmadi"

    s2 = Sent()
    await bot.task_action(FakeCb(s2, f"t:show:{tid}", tg), mk(tg), qc, "uz")
    assert f"t:accept:{tid}" in s2.buttons() and f"t:return:{tid}" in s2.buttons()

    s3 = Sent()
    cb = FakeCb(s3, f"t:accept:{tid}", tg)
    await bot.task_action(cb, mk(tg), qc, "uz")
    assert (await api.task(qc["id"], tid))["status"] == "done"


# ---------------------------------------------------------------- rahbar KPI ko'radi, ishchi ko'ra olmaydi
@pytest.mark.asyncio
async def test_summary_is_gated_by_role(world):
    for login, allowed in (("f_rahbar", True), ("f_prorab", True), ("f_kuzat", True), ("f_ishchi", False)):
        tg = world["tg"][login]
        u = await resolve(tg)
        s = Sent()
        await bot.summary_report(FakeMsg(s, tg), u, "uz")
        if allowed:
            assert "📊" in s.last or t("uz", "rep_empty") in s.last, (login, s.last)
        else:
            assert s.last == t("uz", "no_perm"), (login, s.last)

    # kechikkan / bloklangan ro'yxatlari ham shu qoidada
    for login, allowed in (("f_rahbar", True), ("f_ishchi", False)):
        tg = world["tg"][login]
        u = await resolve(tg)
        for handler in (bot.overdue_list, bot.blocked_list):
            s = Sent()
            await handler(FakeMsg(s, tg), u, "uz")
            if not allowed:
                assert s.last == t("uz", "no_perm")

    # jamoa - faqat admin
    tg = world["tg"]["f_rahbar"]
    u = await resolve(tg)
    s = Sent()
    await bot.team_list(FakeMsg(s, tg), u, "uz")
    assert s.last == t("uz", "no_perm")


# ---------------------------------------------------------------- «Tahrirlash»: matnni qo'lda tuzatish
@pytest.mark.asyncio
async def test_manager_edits_the_task_as_plain_text(world):
    """«✏️ Tahrirlash» bosilganda vazifa oddiy matn bo'lib chiqadi. Rahbar uni nusxa olib,
    xohlagan joyini o'zgartirib, oddiy xabar kabi yuboradi - va o'zgarishlar tushadi."""
    mk = ctx_factory()
    tg = world["tg"]["f_rahbar"]
    u = await resolve(tg)
    st = mk(tg)
    worker = world["users"]["f_ishchi"]
    qc = world["users"]["f_qc"]

    await st.set_data({"project_id": world["project"]["id"], "project_name": world["project"]["name"],
                       "assignee_id": worker["id"], "assignee_name": worker["full_name"],
                       "reviewer_id": qc["id"], "reviewer_name": qc["full_name"],
                       "type_id": world["type"]["id"], "type_name": world["type"]["name"],
                       "title": "Eski sarlavha", "priority": "normal",
                       "planned_start": D(0), "planned_end": D(5), "warnings": []})
    await st.set_state(bot.NewTask.confirm)

    # 1) Tahrirlash -> to'liq matn + nusxa olish tugmasi
    s = Sent()
    cb = FakeCb(s, "nt:edit", tg)
    await bot.nt_edit_menu(cb, st, u, "uz")
    shown = s.last
    assert "Eski sarlavha" in shown and worker["full_name"] in shown
    assert "<pre>" in shown, "matn nusxa olinadigan blok ichida chiqishi kerak"
    copy = [b for m in s.markups if m for row in m.inline_keyboard for b in row if getattr(b, "copy_text", None)]
    assert copy, "nusxa olish tugmasi yo'q"
    assert await st.get_state() == bot.NewTask.edit_all.state

    # 2) foydalanuvchi matnni tuzatib qaytaradi: sarlavha, muddat («ertaga»), muhimlik
    edited = copy[0].copy_text.text \
        .replace("Eski sarlavha", "Yangi sarlavha") \
        .replace(f"Muddat: {(date.today() + timedelta(days=5)).strftime('%d.%m.%Y')}", "Muddat: ertaga") \
        .replace("Muhimlik: O'rta", "Muhimlik: Yuqori")
    s2 = Sent()
    await bot.nt_edit_all(FakeMsg(s2, tg, text=edited), st, u, "uz")
    d = await st.get_data()
    assert d["title"] == "Yangi sarlavha"
    assert d["planned_end"] == D(1), f"«ertaga» sana bo'lib tushmadi: {d['planned_end']}"
    assert d["priority"] == "high"
    assert d["assignee_id"] == worker["id"] and d["reviewer_id"] == qc["id"], "tegilmagan maydonlar o'zgardi"
    assert "Yangi sarlavha" in s2.last and "nt:send" in s2.buttons()
    assert await st.get_state() == bot.NewTask.confirm.state

    # 3) noto'g'ri ism -> taxmin qilinmaydi, eskisi qoladi va ogohlantiriladi
    bad = render.task_block("uz", await st.get_data(),
                            {"assignee": worker["full_name"], "reviewer": qc["full_name"],
                             "project": world["project"]["name"], "type": world["type"]["name"]}) \
        .replace(f"Bajaruvchi: {worker['full_name']}", "Bajaruvchi: Qwerty Zxcvbn")
    s3 = Sent()
    await bot.confirm_text_edit(FakeMsg(s3, tg, text=bad), st, u, "uz")
    d = await st.get_data()
    assert d["assignee_id"] == worker["id"], "noma'lum ism bo'lsa eski bajaruvchi qolishi kerak"
    assert any("Qwerty" in x for x in s3.texts), f"ogohlantirish chiqmadi: {s3.texts}"

    # 4) bitta satr yuborilsa ham darhol tushadi (modelga bormasdan)
    s4 = Sent()
    await bot.confirm_text_edit(FakeMsg(s4, tg, text="Muddat: 15.11.2026"), st, u, "uz")
    d = await st.get_data()
    assert d["planned_end"] == "2026-11-15" and d["title"] == "Yangi sarlavha"

    # 5) blok bo'lmagan oddiy sana eski yo'l bilan tushuniladi - buzilmasligi kerak
    s5 = Sent()
    await bot.nt_edit_all(FakeMsg(s5, tg, text="20.11.2026"), st, u, "uz")
    assert (await st.get_data())["planned_end"] == "2026-11-20"


# ---------------------------------------------------------------- superadmin botda: real "loyiha egasi" oqimi
@pytest.mark.asyncio
async def test_superadmin_bot_menu_has_no_dead_buttons(live_api, world):
    """Superadmin ('admin') haqiqiy foydalanuvchi sifatida botni sinaydi. U hech qachon ijrochi yoki
    tekshiruvchi bo'lmagani uchun 'Vazifalarim/Kunlik hisobot/Muammo/Tekshiruv' tugmalari umuman
    ko'rsatilmasligi kerak (aks holda doim bo'sh chiqib, chalkashtiradi). 'Yangi vazifa' esa uning
    asosiy vazifasi - va 8 tadan ko'p loyiha bo'lganda (real bazada 12 ta) sahifalash tugmasi
    ilgari hech qanday handlerga ulanmagani uchun butunlay o'lik edi - shu yerda tekshiriladi."""
    import os as _os
    import httpx
    base, tok = live_api
    h = {"Authorization": f"Bearer {tok}"}
    with httpx.Client(base_url=base, timeout=20) as c:
        code = c.post("/telegram/link-code", headers=h).json()["code"]
        tg = 900500
        c.post("/telegram/consume-code", json={"code": code, "telegram_user_id": tg},
               headers={"X-Service-Token": _os.environ["SERVICE_TOKEN"]})
        for i in range(10):
            r = c.post("/projects", json={"code": f"SPG-{i:02d}", "name": f"Superadmin sinov {i}"}, headers=h)
            assert r.status_code == 201, r.text

    u = await resolve(tg)
    assert u["role"]["code"] == "admin"

    s = Sent()
    await bot.start(FakeMsg(s, tg), ctx_factory()(), u, "uz")
    keys = s.keys()
    for key in ("btn_my", "btn_report", "btn_problem", "btn_review"):
        assert t("uz", key) not in keys, f"{key} superadminga ko'rinmasligi kerak edi"
    assert t("uz", "btn_new") in keys and t("uz", "btn_team") in keys

    # asosiy oqimlar - hech biri xato bilan yiqilmasligi kerak (hammasi bo'sh ro'yxat qaytaradi)
    for handler in (bot.my_tasks, bot.review_queue, bot.team_list, bot.overdue_list, bot.blocked_list, bot.summary_report):
        s_h = Sent()
        await handler(FakeMsg(s_h, tg), u, "uz")
        assert s_h.texts, f"{handler.__name__} javob bermadi"

    # "Yangi vazifa": 10 ta loyiha bilan sahifalash ishlashi kerak
    st = ctx_factory()()
    s2 = Sent()
    await bot.new_task(FakeMsg(s2, tg), st, u, "uz")
    pg = [b for b in s2.buttons() if b.startswith("ntp_pg:")]
    assert pg, "10 ta loyiha bilan 'keyingi sahifa' tugmasi chiqishi kerak edi"
    s3 = Sent()
    cb = FakeCb(s3, pg[0], tg)
    await bot.ntp_page(cb, st, "uz")
    assert not cb.alerts and s3.markups, "loyiha sahifalash tugmasi javob bermadi"


# ---------------------------------------------------------------- bog'lanmagan foydalanuvchi
@pytest.mark.asyncio
async def test_unlinked_user_is_guided_to_link():
    mk = ctx_factory()
    s = Sent()
    await bot.start(FakeMsg(s, 999999), mk(999999), None, "uz")
    assert "kod" in s.last.lower() or "Sozlamalar" in s.last
    s2 = Sent()
    await bot.my_tasks(FakeMsg(s2, 999999), None, "uz")
    assert s2.last == t("uz", "not_linked")
