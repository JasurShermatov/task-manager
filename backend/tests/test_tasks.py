"""Vazifa oqimi: berish -> boshlash -> dalil bilan topshirish -> qabul / qayta qil."""
from datetime import date, timedelta

D = lambda n: (date.today() + timedelta(days=n)).isoformat()  # noqa: E731


def new_task(boss, world, who="head1", title="Ombor hisobotini tayyorlash", due=None):
    r = boss.post("/tasks", json={"title": title, "assignee_id": world["users"][who]["id"],
                                  "due_at": due or D(3)})
    assert r.status_code == 201, r.text
    return r.json()


def test_task_needs_only_three_fields(boss, world):
    t = new_task(boss, world)
    assert t["code"].startswith("V-")
    assert t["status"] == "new"
    assert t["assignee_name"] == "Sanjar Ergashev"
    assert t["department_name"] == "Ta'minot", "bo'lim boshlig'ining bo'limi kartochkada ko'rinishi kerak"
    # soat ko'rsatilmasa kun oxiri 18:00 bo'ladi
    assert t["due_at"].endswith("T18:00:00"), t["due_at"]


def test_explicit_hour_is_kept(boss, world):
    t = new_task(boss, world, due=f"{D(2)}T14:30")
    assert t["due_at"].endswith("T14:30:00"), t["due_at"]


def test_performer_cannot_create_a_task(users, world):
    r = users["head1"].post("/tasks", json={"title": "Yaramaydi",
                                            "assignee_id": world["users"]["worker1"]["id"],
                                            "due_at": D(1)})
    assert r.status_code == 403


def test_boss_and_assistant_can_task_each_other(boss, users, world):
    a = users["assistant"]
    r = boss.post("/tasks", json={"title": "Assistantga topshiriq", "assignee_id": a.id, "due_at": D(2)})
    assert r.status_code == 201, r.text
    r2 = a.post("/tasks", json={"title": "Boshliqqa eslatma", "assignee_id": boss.id, "due_at": D(2)})
    assert r2.status_code == 201, r2.text


def test_submitting_without_proof_is_refused(boss, users, world):
    """Talab: dalil (rasm/fayl) bilan topshirilsin."""
    t = new_task(boss, world)
    head = users["head1"]
    assert head.post(f"/tasks/{t['id']}/start").json()["status"] == "progress"
    r = head.post(f"/tasks/{t['id']}/submit", {"note": "Bajardim"})
    assert r.status_code == 422 and r.json()["code"] == "PROOF_REQUIRED"

    assert head.prove(t["id"]).status_code == 201
    r = head.post(f"/tasks/{t['id']}/submit", {"note": "Bajardim, rasm ilova"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "submitted" and r.json()["proof_count"] == 1


def test_only_a_manager_accepts_and_the_flow_completes(boss, users, world):
    t = new_task(boss, world, who="worker1")
    w = users["worker1"]
    w.prove(t["id"])
    w.post(f"/tasks/{t['id']}/submit", {"note": "Tayyor"})
    assert w.post(f"/tasks/{t['id']}/accept").status_code == 403
    r = users["assistant"].post(f"/tasks/{t['id']}/accept")
    assert r.status_code == 200 and r.json()["status"] == "done"
    assert r.json()["accepted_by_name"] == "Assistant Aliyev"


def test_return_requires_a_reason_and_new_proof(boss, users, world):
    t = new_task(boss, world, who="worker1")
    w = users["worker1"]
    w.prove(t["id"])
    w.post(f"/tasks/{t['id']}/submit", {"note": "Birinchi urinish"})

    assert boss.post(f"/tasks/{t['id']}/return", {"reason": ""}).status_code == 422
    r = boss.post(f"/tasks/{t['id']}/return", {"reason": "Rasm aniq emas, qaytadan yuboring."})
    assert r.status_code == 200
    assert r.json()["status"] == "progress" and r.json()["return_count"] == 1
    assert r.json()["submit_note"] is None

    # eski dalil bilan qayta topshirib bo'lmaydi
    again = w.post(f"/tasks/{t['id']}/submit", {"note": "O'sha rasm"})
    assert again.status_code == 422 and again.json()["code"] == "PROOF_REQUIRED"
    w.prove(t["id"], "yangi.jpg")
    assert w.post(f"/tasks/{t['id']}/submit", {"note": "Yangi rasm"}).status_code == 200
    # qaytarish sababi izoh bo'lib qoladi
    texts = [c["text"] for c in boss.get(f"/tasks/{t['id']}").json()["comments"]]
    assert any("Rasm aniq emas" in x for x in texts)


def test_performer_sees_only_own_tasks(boss, users, world):
    new_task(boss, world, who="head1", title="Boshliqning ishi")
    new_task(boss, world, who="worker1", title="Xodimning ishi")
    mine = users["worker1"].get("/tasks").json()
    assert mine["items"], "ijrochi o'z vazifalarini ko'rishi kerak"
    assert {i["assignee_id"] for i in mine["items"]} == {users["worker1"].id}
    # boshqasinikiga to'g'ridan-to'g'ri kirib ham bo'lmaydi
    other = boss.get("/tasks", params={"assignee_id": users["head1"].id}).json()["items"][0]
    assert users["worker1"].get(f"/tasks/{other['id']}").status_code == 403


def test_manager_sees_everything_and_can_filter(boss, users, world):
    all_rows = boss.get("/tasks").json()
    assert all_rows["total"] >= 4
    dep = world["departments"]["Ta'minot"]["id"]
    by_dep = boss.get("/tasks", params={"department_id": dep}).json()["items"]
    assert by_dep and all(i["department_name"] == "Ta'minot" for i in by_dep)
    by_status = boss.get("/tasks", params={"status": "done"}).json()["items"]
    assert all(i["status"] == "done" for i in by_status)


def test_overdue_is_visible_and_filterable(boss, world):
    t = new_task(boss, world, who="worker2", title="Kechikkan ish", due=D(-2))
    rows = boss.get("/tasks", params={"overdue": True}).json()["items"]
    assert t["id"] in [i["id"] for i in rows]
    row = next(i for i in rows if i["id"] == t["id"])
    assert row["is_late"] and row["late_days"] >= 1


def test_due_change_is_counted_and_original_kept(boss, world):
    t = new_task(boss, world, who="worker2", due=D(1))
    r = boss.patch(f"/tasks/{t['id']}", {"due_at": D(5)})
    assert r.status_code == 200
    assert r.json()["due_changed_count"] == 1
    assert r.json()["original_due_at"] == t["due_at"], "dastlabki muddat saqlanishi kerak"


def test_comment_from_a_performer_reaches_managers(boss, users, world, client):
    """«Material yo'q» — alohida holat emas, izoh. Boss va assistantga darhol boradi."""
    t = new_task(boss, world, who="worker1")
    r = users["worker1"].post(f"/tasks/{t['id']}/comments", {"text": "Material yo'q, kutyapman"})
    assert r.status_code == 201
    out = client.get("/telegram/outbox", headers={"X-Service-Token": "test-service"}).json()
    # botga ulanmagan bo'lsa navbatda qolmaydi; hech bo'lmasa xatolik bo'lmasligi kerak
    assert isinstance(out, list)
    assert any(c["text"] == "Material yo'q, kutyapman"
               for c in boss.get(f"/tasks/{t['id']}").json()["comments"])


def test_history_records_who_did_what(boss, users, world):
    t = new_task(boss, world, who="worker1")
    w = users["worker1"]
    w.post(f"/tasks/{t['id']}/start")
    w.prove(t["id"])
    w.post(f"/tasks/{t['id']}/submit", {"note": "Tayyor"})
    boss.post(f"/tasks/{t['id']}/accept")
    actions = [h["action"] for h in boss.get(f"/tasks/{t['id']}/history").json()]
    assert actions == ["create", "start", "submit", "accept"]


def test_task_codes_never_collide(boss, world):
    codes = {new_task(boss, world, who="worker2", title=f"Ketma-ketlik {i}")["code"] for i in range(5)}
    assert len(codes) == 5


def test_done_task_cannot_be_edited(boss, users, world):
    t = new_task(boss, world, who="worker1")
    w = users["worker1"]
    w.prove(t["id"])
    w.post(f"/tasks/{t['id']}/submit", {"note": "Tayyor"})
    boss.post(f"/tasks/{t['id']}/accept")
    assert boss.patch(f"/tasks/{t['id']}", {"title": "Yangi nom"}).status_code == 422
    assert boss.post(f"/tasks/{t['id']}/cancel", {"reason": "kech"}).status_code == 422


# ------------------------------------------------- boshqaruvchining o'z vazifalari
def test_manager_sees_only_own_tasks_with_mine(boss, users, world):
    """Boshliq va assistant bir-biriga vazifa beradi — ularga ham «Vazifalarim» kerak.
    `mine=true` bo'lmasa boshqaruvchiga hamma vazifa ko'rinardi."""
    a = users["assistant"]
    r = a.post("/tasks", json={"title": "Boshliqqa: shartnomani imzolang",
                               "assignee_id": boss.id, "due_at": "2026-12-01"})
    assert r.status_code == 201, r.text
    tid = r.json()["id"]

    mine = boss.get("/tasks", params={"mine": "true"}).json()
    assert all(x["assignee_id"] == boss.id for x in mine["items"]), "begona vazifa tushib qolgan"
    assert any(x["id"] == tid for x in mine["items"])

    everything = boss.get("/tasks").json()
    assert everything["total"] > mine["total"], "mine=false bo'lsa boshqaruvchi hammasini ko'radi"


def test_manager_submits_own_task_and_the_other_one_accepts(boss, users, world):
    """To'liq oqim: assistant boshliqqa beradi -> boshliq dalil bilan topshiradi ->
    assistant qabul qiladi. Boshliq o'zinikini o'zi qabul qila olmaydi."""
    a = users["assistant"]
    tid = a.post("/tasks", json={"title": "Boshliq bajaradigan ish", "assignee_id": boss.id,
                                 "due_at": "2026-12-05"}).json()["id"]

    assert boss.post(f"/tasks/{tid}/start").status_code == 200
    assert boss.post(f"/tasks/{tid}/submit", {"note": "Bo'ldi"}).status_code == 422, "dalilsiz o'tmasin"
    boss.prove(tid)
    r = boss.post(f"/tasks/{tid}/submit", {"note": "Imzolandi, nusxasi ilova"})
    assert r.status_code == 200, r.text
    assert r.json()["permissions"]["accept"] is False, "o'z ishini o'zi qabul qilmaydi"

    bad = boss.post(f"/tasks/{tid}/accept")
    assert bad.status_code == 422 and bad.json()["code"] == "SELF_ACCEPT", bad.text
    assert a.post(f"/tasks/{tid}/accept").status_code == 200


def test_self_assigned_task_can_be_closed_by_its_owner(boss):
    """O'ziga o'zi qo'ygan vazifani yopadigan boshqa odam yo'q — bu holat to'siqqa tushmasin."""
    tid = boss.post("/tasks", json={"title": "O'zimga eslatma", "assignee_id": boss.id,
                                    "due_at": "2026-12-09"}).json()["id"]
    boss.prove(tid)
    assert boss.post(f"/tasks/{tid}/submit", {"note": "Tayyor"}).status_code == 200
    assert boss.post(f"/tasks/{tid}/accept").status_code == 200
