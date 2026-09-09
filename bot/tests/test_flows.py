"""Botning haqiqiy handlerlarini soxta Telegram xabarlari bilan, jonli API ustida ishlatish.
Boshliq vazifa beradi, ijrochi dalil bilan topshiradi, boshliq qabul qiladi."""
from __future__ import annotations

import os
import sys
from datetime import date, timedelta

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aiogram.fsm.context import FSMContext  # noqa: E402
from aiogram.fsm.storage.base import StorageKey  # noqa: E402
from aiogram.fsm.storage.memory import MemoryStorage  # noqa: E402

import main as bot  # noqa: E402
import render  # noqa: E402
from i18n import t  # noqa: E402

D = lambda n: (date.today() + timedelta(days=n)).isoformat()  # noqa: E731
PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
       b"\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4"
       b"\x00\x00\x00\x00IEND\xaeB`\x82")


class Sent:
    def __init__(self):
        self.texts: list[str] = []
        self.markups: list = []
        self.docs: list = []

    @property
    def last(self):
        return self.texts[-1] if self.texts else ""

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


class FakePhoto:
    file_id = "photo-1"


class FakeMsg:
    def __init__(self, sink: Sent, tg_id=1, text=None, photo=None):
        self.sink = sink
        self.from_user = FakeUser(tg_id)
        self.message_id = 100
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

    async def answer_document(self, document, caption=None, **kw):
        self.sink.docs.append(document)
        self.sink.texts.append(caption or "")
        self.sink.markups.append(None)
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


class FakeBot:
    """bot.download(...) — rasm yuklab olishni taqlid qiladi."""
    async def download(self, f):
        import io
        return io.BytesIO(PNG)


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
    """Har test o'z event loop'ida ishlaydi — HTTP klientni yangilaymiz.
    Handlerlar isinstance(x, CallbackQuery) bilan ishlaydi, soxta klassni ham qo'shamiz."""
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
    """Boshliq, assistant, bir bo'lim boshlig'i va bir ijrochi — hammasi Telegramga ulangan."""
    import httpx
    base, tok = live_api
    h = {"Authorization": f"Bearer {tok}"}
    with httpx.Client(base_url=base, timeout=20) as c:
        dep = c.post("/departments", json={"name": "Ta'minot"}, headers=h).json()
        made = {}
        for login, name, role, extra in [
            ("assistant", "Assistant Aliyev", "assistant", {}),
            ("head1", "Sanjar Ergashev", "bolim_boshligi", {"department_id": dep["id"]}),
            ("worker1", "Rustam Yusupov", "ijrochi", {"position": "Buxgalter"}),
        ]:
            r = c.post("/users", json={"full_name": name, "login": login, "password": "1234",
                                       "role": role, **extra}, headers=h)
            made[login] = r.json() if r.status_code == 201 else \
                c.get("/users", params={"q": login}, headers=h).json()[0]
        me = c.get("/auth/me", headers=h).json()
        made["boss"] = me

        tg = {}
        for i, (login, u) in enumerate(made.items(), start=1):
            if login == "boss":
                utok = tok
            else:
                utok = c.post("/auth/login", json={"login": login, "password": "1234"}).json()["access_token"]
            code = c.post("/telegram/link-code",
                          headers={"Authorization": f"Bearer {utok}"}).json()["code"]
            tg_id = 900000 + i
            c.post("/telegram/consume-code", json={"code": code, "telegram_user_id": tg_id},
                   headers={"X-Service-Token": os.environ["SERVICE_TOKEN"]})
            tg[login] = tg_id
    return {"users": made, "tg": tg, "department": dep}


async def resolve(tg_id):
    from api import api
    bot.UserMiddleware.invalidate(tg_id)
    return await api.user_by_tg(tg_id)


# ---------------------------------------------------------------- menyu
@pytest.mark.asyncio
async def test_each_role_gets_its_own_menu(world):
    seen = {}
    for login, tg_id in world["tg"].items():
        u = await resolve(tg_id)
        assert u, login
        s = Sent()
        await bot.start(FakeMsg(s, tg_id), ctx_factory()(), u, "uz")
        seen[login] = set(s.keys())
    assert t("uz", "btn_new") in seen["boss"] and t("uz", "btn_new") in seen["assistant"]
    assert seen["boss"] == seen["assistant"], "boshliq va assistant huquqda teng"
    assert t("uz", "btn_my") in seen["head1"] and t("uz", "btn_submit") in seen["head1"]
    assert t("uz", "btn_new") not in seen["head1"], "boshliqdan boshqa hech kim vazifa bermaydi"
    assert t("uz", "btn_report") not in seen["worker1"]


# ---------------------------------------------------------------- to'liq oqim
@pytest.mark.asyncio
async def test_boss_gives_worker_submits_with_proof_boss_accepts(world):
    from api import api
    mk = ctx_factory()
    boss_tg, w_tg = world["tg"]["boss"], world["tg"]["worker1"]
    boss_u, w_u = await resolve(boss_tg), await resolve(w_tg)
    st = mk(boss_tg)

    # 1) boshliq vazifa beradi: kim -> nima -> qachon -> tasdiq
    s = Sent()
    await bot.new_task(FakeMsg(s, boss_tg), st, boss_u, "uz")
    picks = [b for b in s.buttons() if b.startswith("ntw:")]
    assert picks, "odamlar ro'yxati chiqmadi"
    target = f"ntw:{world['users']['worker1']['id']}"
    assert target in picks
    await bot.who_chosen(FakeCb(s, target, boss_tg), st, boss_u, "uz")
    await bot.nt_title(FakeMsg(Sent(), boss_tg, text="Ombor hisobotini tayyorlash"), st, boss_u, "uz")
    s2 = Sent()
    await bot.nt_due(FakeCb(s2, "nt:due:3", boss_tg), st, boss_u, "uz")
    card = s2.last
    assert "Ombor hisobotini" in card and "Rustam Yusupov" in card
    assert "nt:send" in s2.buttons()

    s3 = Sent()
    await bot.nt_send(FakeCb(s3, "nt:send", boss_tg), st, boss_u, "uz")
    code = next(w for x in s3.texts for w in x.replace("<b>", " ").replace("</b>", " ").split()
                if w.startswith("V-"))
    tk = await api.task_by_code(boss_u["id"], code)
    assert tk["assignee_id"] == world["users"]["worker1"]["id"]
    assert tk["due_at"][:10] == D(3)

    # 2) ijrochi ko'radi va topshirishni boshlaydi
    wst = mk(w_tg)
    s4 = Sent()
    await bot.my_tasks(FakeMsg(s4, w_tg), w_u, "uz")
    assert code in " ".join(s4.texts)

    s5 = Sent()
    await bot.submit_pick(FakeMsg(s5, w_tg), wst, w_u, "uz")
    pick = [b for b in s5.buttons() if b.startswith("sbp:")][0]
    await bot.submit_chosen(FakeCb(s5, pick, w_tg), wst, w_u, "uz")

    # 3) matn -> rasm -> tayyor
    await bot.submit_note(FakeMsg(Sent(), w_tg, text="Hisobot tayyor"), wst, w_u, "uz")
    s6 = Sent()
    # dalilsiz "Tayyor" bosilsa - rad etiladi
    await bot.submit_finish(FakeMsg(s6, w_tg, text=t("uz", "btn_done")), wst, w_u, "uz")
    assert t("uz", "sb_need_file") in s6.texts

    s7 = Sent()
    await bot.submit_file(FakeMsg(s7, w_tg, photo=[FakePhoto()]), wst, w_u, "uz", FakeBot())
    assert "1" in s7.last
    s8 = Sent()
    await bot.submit_finish(FakeMsg(s8, w_tg, text=t("uz", "btn_done")), wst, w_u, "uz")
    assert code in " ".join(s8.texts)

    tk = await api.task_by_code(boss_u["id"], code)
    assert tk["status"] == "submitted" and tk["proof_count"] == 1

    # 4) boshliq xabarning o'zidan qabul qiladi
    s9 = Sent()
    await bot.task_action(FakeCb(s9, f"t:acc:{tk['id']}", boss_tg), mk(boss_tg), boss_u, "uz")
    tk = await api.task_by_code(boss_u["id"], code)
    assert tk["status"] == "done" and tk["accepted_by"] == boss_u["id"]
    world["done_code"] = code


@pytest.mark.asyncio
async def test_boss_returns_a_task_with_a_reason(world):
    from api import api
    mk = ctx_factory()
    boss_tg, w_tg = world["tg"]["boss"], world["tg"]["head1"]
    boss_u, w_u = await resolve(boss_tg), await resolve(w_tg)
    tk = await api.create_task(boss_u["id"], {"title": "Qaytariladigan ish",
                                              "assignee_id": world["users"]["head1"]["id"],
                                              "due_at": D(2)})
    wst = mk(w_tg)
    await bot.begin_submit(FakeMsg(Sent(), w_tg), wst, w_u, "uz", tk["id"])
    await bot.submit_note(FakeMsg(Sent(), w_tg, text="Bajardim"), wst, w_u, "uz")
    await bot.submit_file(FakeMsg(Sent(), w_tg, photo=[FakePhoto()]), wst, w_u, "uz", FakeBot())
    await bot.submit_finish(FakeMsg(Sent(), w_tg, text=t("uz", "btn_done")), wst, w_u, "uz")

    bst = mk(boss_tg)
    s = Sent()
    await bot.task_action(FakeCb(s, f"t:ret:{tk['id']}", boss_tg), bst, boss_u, "uz")
    assert t("uz", "ret_reason") in s.texts
    s2 = Sent()
    await bot.ret_reason(FakeMsg(s2, boss_tg, text="Rasm aniq emas"), bst, boss_u, "uz")
    again = await api.task(boss_u["id"], tk["id"])
    assert again["status"] == "progress" and again["return_count"] == 1

    # eski dalil bilan qayta topshirib bo'lmaydi
    wst2 = mk(w_tg)
    await bot.begin_submit(FakeMsg(Sent(), w_tg), wst2, w_u, "uz", tk["id"])
    await bot.submit_note(FakeMsg(Sent(), w_tg, text="O'sha rasm"), wst2, w_u, "uz")
    s3 = Sent()
    await bot.submit_file(FakeMsg(s3, w_tg, photo=[FakePhoto()]), wst2, w_u, "uz", FakeBot())
    await bot.submit_finish(FakeMsg(s3, w_tg, text=t("uz", "btn_done")), wst2, w_u, "uz")
    assert (await api.task(boss_u["id"], tk["id"]))["status"] == "submitted"


# ---------------------------------------------------------------- tahrirlash
@pytest.mark.asyncio
async def test_edit_shows_the_task_as_plain_text(world):
    mk = ctx_factory()
    boss_tg = world["tg"]["boss"]
    boss_u = await resolve(boss_tg)
    st = mk(boss_tg)
    await st.set_data({"title": "Eski sarlavha", "assignee_id": world["users"]["worker1"]["id"],
                       "assignee_name": "Rustam Yusupov", "due_at": f"{D(5)}T18:00"})
    await st.set_state(bot.NewTask.confirm)

    s = Sent()
    await bot.nt_edit(FakeCb(s, "nt:edit", boss_tg), st, boss_u, "uz")
    assert "<pre>" in s.last and "Eski sarlavha" in s.last
    copy = [b for m in s.markups if m for row in m.inline_keyboard for b in row
            if getattr(b, "copy_text", None)]
    assert copy, "nusxa olish tugmasi yo'q"

    edited = copy[0].copy_text.text.replace("Eski sarlavha", "Yangi sarlavha")
    edited = edited.replace(render.fmt_due(f"{D(5)}T18:00"), "ertaga kechgacha")
    s2 = Sent()
    await bot.nt_edit_all(FakeMsg(s2, boss_tg, text=edited), st, boss_u, "uz")
    d = await st.get_data()
    assert d["title"] == "Yangi sarlavha"
    assert d["due_at"][:10] == D(1), f"«ertaga» sana bo'lmadi: {d['due_at']}"
    assert d["assignee_id"] == world["users"]["worker1"]["id"], "tegilmagan maydon o'zgardi"


@pytest.mark.asyncio
async def test_unknown_name_is_not_guessed(world):
    mk = ctx_factory()
    boss_tg = world["tg"]["boss"]
    boss_u = await resolve(boss_tg)
    st = mk(boss_tg)
    await st.set_data({"title": "Ish", "assignee_id": world["users"]["worker1"]["id"],
                       "assignee_name": "Rustam Yusupov", "due_at": f"{D(2)}T18:00"})
    await st.set_state(bot.NewTask.confirm)
    s = Sent()
    await bot.confirm_text(FakeMsg(s, boss_tg, text="Bajaruvchi: Qwerty Zxcvbn"), st, boss_u, "uz")
    d = await st.get_data()
    assert d["assignee_id"] == world["users"]["worker1"]["id"], "noma'lum ism eskisini almashtirdi"
    assert any("Qwerty" in x for x in s.texts), "ogohlantirish chiqmadi"


# ---------------------------------------------------------------- hisobot
@pytest.mark.asyncio
async def test_report_shows_a_table_and_offers_files(world):
    boss_tg = world["tg"]["boss"]
    boss_u = await resolve(boss_tg)
    s = Sent()
    await bot.report_cmd(FakeMsg(s, boss_tg), boss_u, "uz")
    assert "<pre>" in s.last and "JAMI" in s.last
    assert "rep:dl:xlsx:month" in s.buttons() and "rep:week" in s.buttons()

    s2 = Sent()
    await bot.report_download(FakeCb(s2, "rep:dl:csv:month", boss_tg), boss_u, "uz")
    assert s2.docs, "fayl yuborilmadi"
    assert s2.docs[0].filename.endswith(".csv")

    s3 = Sent()
    await bot.report_download(FakeCb(s3, "rep:dl:xlsx:month", boss_tg), boss_u, "uz")
    assert s3.docs[0].filename.endswith(".xlsx")


@pytest.mark.asyncio
async def test_performers_cannot_reach_manager_screens(world):
    w_tg = world["tg"]["worker1"]
    w_u = await resolve(w_tg)
    for handler in (bot.report_cmd, bot.people_list, bot.submitted_list, bot.late_list):
        s = Sent()
        await handler(FakeMsg(s, w_tg), w_u, "uz")
        assert s.last == t("uz", "no_perm"), handler.__name__


@pytest.mark.asyncio
async def test_people_screen_lists_the_team(world):
    boss_tg = world["tg"]["boss"]
    boss_u = await resolve(boss_tg)
    s = Sent()
    await bot.people_list(FakeMsg(s, boss_tg), boss_u, "uz")
    text = " ".join(s.texts)
    assert "Sanjar Ergashev" in text and "Rustam Yusupov" in text
    assert "Assistant Aliyev" not in text, "boshqaruvchilar ijrochilar ro'yxatida chiqmasin"


# ---------------------------------------------------------------- bog'lanmagan
@pytest.mark.asyncio
async def test_unlinked_user_is_guided_to_link():
    s = Sent()
    await bot.start(FakeMsg(s, 999999), ctx_factory()(999999), None, "uz")
    assert "kod" in s.last.lower() or "Kod" in s.last
    s2 = Sent()
    await bot.my_tasks(FakeMsg(s2, 999999), None, "uz")
    assert s2.last == t("uz", "not_linked")


@pytest.mark.asyncio
async def test_api_outage_does_not_look_like_being_unlinked():
    """Eng og'riqli xato shu edi: API bir zumga javob bermasa, bot «hisobingizni
    bog'lang» deb kod so'rardi va odam har safar qaytadan bog'lardi."""
    tg = 888888
    bot.UserMiddleware.down.add(tg)
    try:
        s = Sent()
        await bot.my_tasks(FakeMsg(s, tg), None, "uz")
        assert s.last == t("uz", "api_wait")
        s2 = Sent()
        await bot.start(FakeMsg(s2, tg), ctx_factory()(tg), None, "uz")
        assert s2.last == t("uz", "api_wait")
        assert t("uz", "ask_code") not in s2.texts, "kod so'ralmasligi kerak"
    finally:
        bot.UserMiddleware.down.discard(tg)
