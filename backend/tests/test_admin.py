"""Administratsiya: bo'limlar va xodimlar. Faqat boss va assistant kira oladi."""


def test_boss_and_assistant_have_the_same_rights(boss, users, world):
    """Talab: boss va assistant huquqda aynan teng."""
    a = users["assistant"]
    r = a.post("/departments", json={"name": "Assistant ochgan bo'lim"})
    assert r.status_code == 201, r.text
    dep_id = r.json()["id"]
    assert a.patch(f"/departments/{dep_id}", {"name": "Nomi o'zgardi", "sort_order": 5}).status_code == 200
    r = a.post("/users", json={"full_name": "Assistant qo'shgan", "login": "aq1",
                               "password": "1234", "role": "ijrochi"})
    assert r.status_code == 201, r.text
    assert a.post(f"/users/{r.json()['id']}/block").status_code == 200
    assert a.delete(f"/departments/{dep_id}").status_code == 200


def test_performers_cannot_reach_administration(users):
    for who in ("head1", "worker1"):
        u = users[who]
        assert u.post("/departments", json={"name": "Yaramaydi"}).status_code == 403
        assert u.post("/users", json={"full_name": "X", "login": "x9", "password": "1234",
                                      "role": "ijrochi"}).status_code == 403
        assert u.get("/reports/summary").status_code == 403


def test_department_can_have_only_one_head(boss, world):
    dep = world["departments"]["Ta'minot"]["id"]
    r = boss.post("/users", json={"full_name": "Ikkinchi boshliq", "login": "head_dup",
                                  "password": "1234", "role": "bolim_boshligi", "department_id": dep})
    assert r.status_code == 422, r.text
    assert r.json()["code"] == "DEPARTMENT_TAKEN"
    assert world["users"]["head1"]["full_name"] in r.json()["message"]


def test_head_needs_a_department_and_worker_never_gets_one(boss):
    r = boss.post("/users", json={"full_name": "Bo'limsiz boshliq", "login": "nodep",
                                  "password": "1234", "role": "bolim_boshligi"})
    assert r.status_code == 422 and r.json()["field_errors"].get("department_id") == "required"
    # ijrochiga bo'lim berilsa - e'tiborga olinmaydi, u asosiy bo'lim xodimi
    r = boss.post("/users", json={"full_name": "Asosiy xodim", "login": "mainw",
                                  "password": "1234", "role": "ijrochi", "department_id": 1})
    assert r.status_code == 201 and r.json()["department_id"] is None
    boss.post(f"/users/{r.json()['id']}/block")


def test_department_listing_shows_its_head(boss, world):
    rows = {d["name"]: d for d in boss.get("/departments").json()}
    assert rows["Ta'minot"]["head_name"] == "Sanjar Ergashev"
    assert rows["Qurilish"]["head_id"] == world["users"]["head2"]["id"]


def test_department_with_a_head_is_not_deleted_silently(boss, world):
    dep = world["departments"]["Qurilish"]["id"]
    r = boss.delete(f"/departments/{dep}")
    assert r.status_code == 422 and r.json()["code"] == "DEPARTMENT_HAS_HEAD"
    assert "Bekzod" in r.json()["message"], "xabar kimni ko'chirish kerakligini aytishi kerak"


def test_person_with_open_tasks_is_not_blocked(boss, world, users):
    """Bloklab qo'ysak vazifa ochiq qolib, hech kimga ko'rinmay ketardi."""
    w = world["users"]["worker2"]["id"]
    t = boss.post("/tasks", json={"title": "Bloklashni sinash", "assignee_id": w,
                                  "due_at": "2026-12-01"})
    assert t.status_code == 201, t.text
    r = boss.post(f"/users/{w}/block")
    assert r.status_code == 422 and r.json()["code"] == "HAS_OPEN_TASKS"
    assert r.json()["open_tasks"] >= 1
    boss.post(f"/tasks/{t.json()['id']}/cancel", {"reason": "sinov tugadi"})


def test_boss_cannot_block_himself_or_the_last_boss(boss):
    r = boss.post(f"/users/{boss.id}/block")
    assert r.status_code == 422 and r.json()["code"] == "SELF_BLOCK"


def test_login_must_be_unique(boss):
    r = boss.post("/users", json={"full_name": "Takror", "login": "worker1",
                                  "password": "1234", "role": "ijrochi"})
    assert r.status_code == 422 and r.json()["code"] == "LOGIN_TAKEN"


def test_everyone_can_change_their_own_language(users):
    u = users["worker1"]
    assert u.patch("/auth/me", {"lang": "ru"}).json()["lang"] == "ru"
    assert u.patch("/auth/me", {"lang": "uz"}).json()["lang"] == "uz"


# ------------------------------------------------- assistant hisoblari: faqat boshliq
def test_only_the_boss_manages_assistant_accounts(boss, users, world):
    """Talab: boshliqning yagona ustunligi — assistant hisoblarini CRUD qilish.
    Assistant esa o'ziga teng hisob ocha olmaydi."""
    a = users["assistant"]
    r = a.post("/users", json={"full_name": "Yashirin assistant", "login": "asst_x",
                               "password": "1234", "role": "assistant"})
    assert r.status_code == 403, r.text
    assert r.json()["code"] == "BOSS_ONLY", r.text

    # boshliq esa ocha oladi
    r = boss.post("/users", json={"full_name": "Ikkinchi assistant", "login": "asst2",
                                  "password": "1234", "role": "assistant"})
    assert r.status_code == 201, r.text
    new_id = r.json()["id"]

    # assistant boshqa assistantga tegolmaydi: tahrir, parol, blok
    assert a.patch(f"/users/{new_id}", {"full_name": "Boshqa ism"}).status_code == 403
    assert a.post(f"/users/{new_id}/password", {"password": "5678"}).status_code == 403
    assert a.post(f"/users/{new_id}/block").status_code == 403

    # boshliq hammasini qila oladi
    assert boss.patch(f"/users/{new_id}", {"full_name": "Ikkinchi assistant A."}).status_code == 200
    assert boss.post(f"/users/{new_id}/password", {"password": "5678"}).status_code == 200
    assert boss.post(f"/users/{new_id}/block").status_code == 200
    assert boss.post(f"/users/{new_id}/unblock").status_code == 200


def test_assistant_cannot_touch_the_boss(boss, users):
    a = users["assistant"]
    assert a.post(f"/users/{boss.id}/block").status_code == 403
    assert a.patch(f"/users/{boss.id}", {"full_name": "Yangi boshliq"}).status_code == 403
    assert a.post(f"/users/{boss.id}/password", {"password": "1234"}).status_code == 403


def test_assistant_cannot_promote_anyone_to_the_top(users, world):
    """Ijrochini assistantga ko'tarish ham tepa qatlamga tegish — faqat boshliqda."""
    a = users["assistant"]
    worker = world["users"]["worker1"]["id"]
    assert a.patch(f"/users/{worker}", {"role": "assistant"}).status_code == 403
    assert a.patch(f"/users/{worker}", {"role": "boss"}).status_code == 403


def test_assistant_still_manages_everyone_below(boss, users, world):
    """Pastdagi xodimlar kesimida boss va assistant teng — bu buzilmasligi kerak."""
    a = users["assistant"]
    r = a.post("/users", json={"full_name": "Yangi ijrochi", "login": "ij_new",
                               "password": "1234", "role": "ijrochi"})
    assert r.status_code == 201, r.text
    uid = r.json()["id"]
    assert a.patch(f"/users/{uid}", {"position": "Ta'minotchi"}).status_code == 200
    assert a.post(f"/users/{uid}/password", {"password": "4321"}).status_code == 200
    assert a.post(f"/users/{uid}/block").status_code == 200


def test_assistant_can_still_edit_own_profile(users):
    a = users["assistant"]
    assert a.patch("/auth/me", {"full_name": "Assistant Aliyev"}).status_code == 200
    assert a.patch(f"/users/{a.id}", {"lang": "ru"}).status_code == 200
    assert a.patch(f"/users/{a.id}", {"lang": "uz"}).status_code == 200


# ------------------------------------------------- bot bilan bog'lanish
def test_unlinking_tells_the_bot_at_once(client, boss, users, world):
    """Bot foydalanuvchini bir necha daqiqa saqlab turadi (tezlik uchun). Shuning uchun
    web'dagi «Uzish» alohida xabar qoldiradi — bot uni o'qib xotirasini tozalaydi.
    Bo'lmasa odam uzganini o'ylaydi, bot esa ishlab turaveradi."""
    H = {"X-Service-Token": "test-service"}
    client.get("/telegram/link-revocations", headers=H)     # eskisini bo'shatamiz

    w = users["worker1"]
    code = w.post("/telegram/link-code").json()["code"]
    tg = 770001
    assert client.post("/telegram/consume-code", json={"code": code, "telegram_user_id": tg},
                       headers=H).status_code == 200
    assert client.get(f"/telegram/user-by-tg/{tg}", headers=H).status_code == 200

    assert w.delete("/telegram/unlink").status_code == 200
    r = client.get("/telegram/link-revocations", headers=H)
    assert r.status_code == 200 and tg in r.json(), r.text
    assert client.get("/telegram/link-revocations", headers=H).json() == [], "bir marta o'qiladi"
    assert client.get(f"/telegram/user-by-tg/{tg}", headers=H).status_code == 404


def test_blocking_a_person_also_cuts_their_bot(client, boss, world):
    """Bloklangan odam bot orqali ishlashda davom etmasin."""
    H = {"X-Service-Token": "test-service"}
    client.get("/telegram/link-revocations", headers=H)
    r = boss.post("/users", json={"full_name": "Bloklanadigan", "login": "blk1",
                                  "password": "1234", "role": "ijrochi"})
    uid = r.json()["id"]
    tok = client.post("/auth/login", json={"login": "blk1", "password": "1234"}).json()["access_token"]
    code = client.post("/telegram/link-code", headers={"Authorization": f"Bearer {tok}"}).json()["code"]
    tg = 770002
    client.post("/telegram/consume-code", json={"code": code, "telegram_user_id": tg}, headers=H)

    assert boss.post(f"/users/{uid}/block").status_code == 200
    assert tg in client.get("/telegram/link-revocations", headers=H).json()
    assert client.get(f"/telegram/user-by-tg/{tg}", headers=H).status_code == 404

    # blok bog'lanishni uzmaydi — blokdan chiqsa bot yana ishlaydi
    assert boss.post(f"/users/{uid}/unblock").status_code == 200
    assert client.get(f"/telegram/user-by-tg/{tg}", headers=H).status_code == 200
    tok2 = client.post("/auth/login", json={"login": "blk1", "password": "1234"}).json()["access_token"]
    client.delete("/telegram/unlink", headers={"Authorization": f"Bearer {tok2}"})
    client.get("/telegram/link-revocations", headers=H)
