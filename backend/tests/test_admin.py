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
