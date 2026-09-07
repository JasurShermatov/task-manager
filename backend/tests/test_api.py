"""Acceptance tests — one per criterion in TZ §13, plus permission/scope checks."""
import io
from datetime import date, timedelta

import pytest

from conftest import U

TODAY = date.today()
D = lambda n: (TODAY + timedelta(days=n)).isoformat()

PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
       b"\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82")


# ---------------------------------------------------------------- fixtures
@pytest.fixture(scope="session")
def admin(client):
    return U(client, "admin", "admin12345")


@pytest.fixture(scope="session")
def world(client, admin):
    """Creates project/locations/users once; returns handles."""
    roles = {r["code"]: r["id"] for r in admin.get("/roles").json()}
    pr = admin.get("/projects").json()[0]
    locs = admin.get("/locations", params={"project_id": pr["id"]}).json()
    block = next(l for l in locs if l["kind"] == "block")
    floors = [l for l in locs if l["kind"] == "floor"]

    # second project + block (for scope tests)
    pr2 = admin.post("/projects", json={"code": "SAFF-02", "name": "Ikkinchi obyekt"}).json()
    block2 = admin.post("/locations", json={"project_id": pr2["id"], "name": "B blok", "kind": "block"}).json()

    def mkuser(login, name, role, scope_type="system", scope_id=None):
        r = admin.post("/users", json={"full_name": name, "login": login, "password": "parol1234567",
                                       "role_id": roles[role], "scope_type": scope_type, "scope_id": scope_id})
        assert r.status_code == 201, r.text
        return r.json()

    mkuser("rahbar", "Rahbar Rahbarov", "rahbar", "project", pr["id"])
    mkuser("prorab", "Prorab Prorabov", "prorab", "location", block["id"])
    mkuser("ishchi", "Rustam Ergashev", "bajaruvchi")
    mkuser("ishchi2", "Sardor Karimov", "bajaruvchi")
    mkuser("qc", "Doniyor Toshmatov", "tekshiruvchi", "project", pr["id"])
    mkuser("kuzat", "Kuzatuvchi K", "kuzatuvchi", "project", pr["id"])
    mkuser("chet", "Chet Odam", "prorab", "location", block2["id"])

    types = admin.get("/task-types").json()
    beton = next(t for t in types if t["name"] == "Beton ishlari")
    umumiy = next(t for t in types if t["name"] == "Umumiy vazifa")
    return {"project": pr, "project2": pr2, "block": block, "floors": floors, "roles": roles,
            "beton": beton, "umumiy": umumiy}


@pytest.fixture(scope="session")
def users(client, world):
    return {k: U(client, k, "parol1234567") for k in ("rahbar", "prorab", "ishchi", "ishchi2", "qc", "kuzat", "chet")}


def mktask(actor, world, **over):
    body = {"project_id": world["project"]["id"], "location_id": world["floors"][0]["id"],
            "type_id": world["umumiy"]["id"], "title": "Test vazifa", "assignee_id": None,
            "reviewer_id": None, "planned_start": D(0), "planned_end": D(3)}
    body.update(over)
    r = actor.post("/tasks", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def ready_for_review(actor, task):
    """Tick every required checklist item and attach every required evidence kind."""
    det = actor.get(f"/tasks/{task['id']}").json()
    req = [c["id"] for c in det["checklist"] if c["is_required"] and not c["is_done"]]
    if req:
        r = actor.patch(f"/tasks/{task['id']}/checklist", {"items": [{"id": i, "is_done": True} for i in req]})
        assert r.status_code == 200, r.text
    have = {a["kind"] for a in det["attachments"]}
    for kind in det["required_evidence_kinds"]:
        if kind in have:
            continue
        r = actor.upload(f"/tasks/{task['id']}/attachments",
                         files={"file": (f"{kind}.png", PNG, "image/png")}, data={"kind": kind})
        assert r.status_code == 201, r.text


# ---------------------------------------------------------------- basics
def test_health_and_login(client, admin):
    assert client.get("/health").json()["ok"] is True
    assert admin.role == "admin"
    assert "tasks.create" in admin.perms
    bad = client.post("/auth/login", json={"login": "admin", "password": "nope"})
    assert bad.status_code == 401
    assert bad.json()["code"] == "UNAUTHORIZED"


def test_refresh_and_logout(client, world):
    u = U(client, "rahbar", "parol1234567")
    r = client.post("/auth/refresh", json={"refresh_token": u.refresh})
    assert r.status_code == 200
    new = r.json()
    # old refresh token is single-use
    assert client.post("/auth/refresh", json={"refresh_token": u.refresh}).status_code == 401
    assert client.post("/auth/logout", json={"refresh_token": new["refresh_token"]}).status_code == 200


def test_meta(admin):
    m = admin.get("/meta").json()
    assert "material_yoq" in m["block_reasons"]
    assert m["statuses"][0] == "plan"


# ---------------------------------------------------------------- §13.1 create + notify
def test_01_create_task_appears_in_plan_and_notifies(users, world):
    t = mktask(users["rahbar"], world, title="Monolit plita — betonlash",
               assignee_id=users["ishchi"].id, reviewer_id=users["qc"].id)
    assert t["status"] == "plan"
    assert t["code"].startswith("V-")
    assert t["assignee_name"] == "Rustam Ergashev"
    lst = users["rahbar"].get("/tasks", params={"status": "plan"}).json()
    assert any(x["id"] == t["id"] for x in lst["items"])
    n = users["ishchi"].get("/notifications").json()
    assert any(x["event"] == "assigned" and x["task_id"] == t["id"] for x in n)


# ---------------------------------------------------------------- §13.2 start
def test_02_start_sets_actual_start(users, world):
    t = mktask(users["rahbar"], world, assignee_id=users["ishchi"].id, reviewer_id=users["qc"].id)
    r = users["ishchi"].post(f"/tasks/{t['id']}/start")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "progress"
    assert r.json()["actual_start"]


# ---------------------------------------------------------------- §13.3 dependencies
def test_03_dependency_blocks_start(users, world):
    a = mktask(users["rahbar"], world, title="A blok ishi", assignee_id=users["ishchi"].id, reviewer_id=users["qc"].id)
    b = mktask(users["rahbar"], world, title="B blok ishi", assignee_id=users["ishchi"].id, reviewer_id=users["qc"].id,
               depends_on=[a["id"]])
    r = users["ishchi"].post(f"/tasks/{b['id']}/start")
    assert r.status_code == 409 and r.json()["code"] == "DEPENDENCY_NOT_DONE"
    assert a["code"] in r.json()["codes"]
    detail = users["ishchi"].get(f"/tasks/{b['id']}").json()
    assert detail["dependency_pending"] == [a["code"]]


def test_03b_dependency_cycle_rejected(users, world):
    a = mktask(users["rahbar"], world, title="Halqa 1", assignee_id=users["ishchi"].id, reviewer_id=users["qc"].id)
    b = mktask(users["rahbar"], world, title="Halqa 2", assignee_id=users["ishchi"].id, reviewer_id=users["qc"].id,
               depends_on=[a["id"]])
    r = users["rahbar"].post(f"/tasks/{a['id']}/dependencies", json={"depends_on_task_id": b["id"]})
    assert r.status_code == 422 and r.json()["code"] == "DEPENDENCY_CYCLE"


# ---------------------------------------------------------------- §13.4/13.5 checklist + evidence
def test_04_05_required_checklist_and_evidence(users, world):
    t = mktask(users["rahbar"], world, type_id=world["beton"]["id"], title="Beton",
               assignee_id=users["ishchi"].id, reviewer_id=users["qc"].id)
    assert t["checklist_total"] == 4
    assert t["required_evidence_kinds"] == ["before", "during", "after"]
    users["ishchi"].post(f"/tasks/{t['id']}/start")

    r = users["ishchi"].post(f"/tasks/{t['id']}/submit-review")
    assert r.status_code == 422 and r.json()["code"] == "REQUIRED_CHECKLIST"
    assert len(r.json()["items"]) == 3

    det = users["ishchi"].get(f"/tasks/{t['id']}").json()
    req = [c["id"] for c in det["checklist"] if c["is_required"]]
    upd = users["ishchi"].patch(f"/tasks/{t['id']}/checklist", {"items": [{"id": i, "is_done": True} for i in req]})
    assert upd.status_code == 200
    assert upd.json()["checklist_done"] == 3
    assert upd.json()["progress_percent"] == 75  # 3 of 4 items — computed server-side

    r = users["ishchi"].post(f"/tasks/{t['id']}/submit-review")
    assert r.status_code == 422 and r.json()["code"] == "REQUIRED_EVIDENCE"
    assert set(r.json()["kinds"]) == {"before", "during", "after"}

    for kind in ("before", "during", "after"):
        up = users["ishchi"].upload(f"/tasks/{t['id']}/attachments",
                                    files={"file": (f"{kind}.png", PNG, "image/png")}, data={"kind": kind})
        assert up.status_code == 201, up.text
        assert up.json()["url"].startswith("http")
    r = users["ishchi"].post(f"/tasks/{t['id']}/submit-review")
    assert r.status_code == 200 and r.json()["status"] == "review"


# ---------------------------------------------------------------- §13.6/13.7 review, self-accept
def test_06_07_accept_return_and_self_accept_forbidden(users, world):
    t = mktask(users["rahbar"], world, assignee_id=users["ishchi"].id, reviewer_id=users["qc"].id)
    users["ishchi"].post(f"/tasks/{t['id']}/start")
    ready_for_review(users["ishchi"], t)
    assert users["ishchi"].post(f"/tasks/{t['id']}/submit-review").status_code == 200

    # assignee cannot accept own work — no button, and the request is refused
    det = users["ishchi"].get(f"/tasks/{t['id']}").json()
    assert det["permissions"]["accept"] is False
    r = users["ishchi"].post(f"/tasks/{t['id']}/accept")
    assert r.status_code == 403  # bajaruvchi lacks tasks.accept at all

    # a reviewer who is also the assignee is refused with SELF_ACCEPT_FORBIDDEN
    t2 = mktask(users["rahbar"], world, assignee_id=users["qc"].id, reviewer_id=users["qc"].id)
    users["rahbar"].post(f"/tasks/{t2['id']}/start")
    ready_for_review(users["rahbar"], t2)
    assert users["rahbar"].post(f"/tasks/{t2['id']}/submit-review").status_code == 200
    r = users["qc"].post(f"/tasks/{t2['id']}/accept")
    assert r.status_code == 409 and r.json()["code"] == "SELF_ACCEPT_FORBIDDEN"

    # return needs a reason and increments return_count
    assert users["qc"].post(f"/tasks/{t['id']}/return", json={"reason": ""}).status_code == 422
    r = users["qc"].post(f"/tasks/{t['id']}/return", json={"reason": "Yuza tekis emas"})
    assert r.status_code == 200 and r.json()["status"] == "progress" and r.json()["return_count"] == 1
    assert any(n["event"] == "returned" for n in users["ishchi"].get("/notifications").json())

    assert users["ishchi"].post(f"/tasks/{t['id']}/submit-review").status_code == 200
    r = users["qc"].post(f"/tasks/{t['id']}/accept")
    assert r.status_code == 200 and r.json()["status"] == "done" and r.json()["progress_percent"] == 100
    assert r.json()["actual_end"]

    hist = [h["action"] for h in users["qc"].get(f"/tasks/{t['id']}/history").json()]
    assert {"create", "start", "submit_review", "return", "accept"} <= set(hist)


# ---------------------------------------------------------------- §13.8 block
def test_08_block_requires_reason_and_returns_to_previous(users, world):
    t = mktask(users["rahbar"], world, assignee_id=users["ishchi"].id, reviewer_id=users["qc"].id)
    users["ishchi"].post(f"/tasks/{t['id']}/start")
    assert users["ishchi"].post(f"/tasks/{t['id']}/block", json={"reason": "material_yoq", "note": ""}).status_code == 422
    r = users["ishchi"].post(f"/tasks/{t['id']}/block", json={"reason": "material_yoq", "note": "Sement kelmadi"})
    assert r.status_code == 200
    assert r.json()["status"] == "blocked" and r.json()["previous_status"] == "progress"
    assert r.json()["blocked_reason"] == "material_yoq"
    r = users["ishchi"].post(f"/tasks/{t['id']}/unblock")
    assert r.json()["status"] == "progress" and r.json()["blocked_reason"] is None
    assert any(n["event"] == "blocked" for n in users["rahbar"].get("/notifications").json())


# ---------------------------------------------------------------- §13.9 daily progress
def test_09_daily_progress_recomputes_quantity(users, world):
    t = mktask(users["rahbar"], world, assignee_id=users["ishchi"].id, reviewer_id=users["qc"].id,
               planned_quantity=240, unit="m3", checklist=[])
    users["ishchi"].post(f"/tasks/{t['id']}/start")
    r = users["ishchi"].post(f"/tasks/{t['id']}/daily-progress", json={"date": D(0), "quantity": 100, "workers_count": 8})
    assert r.status_code == 201 and r.json()["is_duplicate"] is False
    det = users["ishchi"].get(f"/tasks/{t['id']}").json()
    assert float(det["actual_quantity"]) == 100 and det["progress_percent"] == 42

    # §5.9 second report the same day is kept but flagged and not counted
    dup = users["ishchi"].post(f"/tasks/{t['id']}/daily-progress", json={"date": D(0), "quantity": 50})
    assert dup.json()["is_duplicate"] is True
    det = users["ishchi"].get(f"/tasks/{t['id']}").json()
    assert float(det["actual_quantity"]) == 100

    # over plan flag
    users["ishchi"].post(f"/tasks/{t['id']}/daily-progress", json={"date": D(1), "quantity": 200})
    det = users["ishchi"].get(f"/tasks/{t['id']}").json()
    assert det["quantity_over_plan"] is True and det["progress_percent"] == 100

    # client cannot write computed fields
    r = users["rahbar"].patch(f"/tasks/{t['id']}", {"row_version": det["row_version"], "progress_percent": 10})
    assert r.status_code in (200, 422)
    assert users["rahbar"].get(f"/tasks/{t['id']}").json()["progress_percent"] == 100


# ---------------------------------------------------------------- §13.10 filters & KPI
def test_10_overdue_blocked_filters_and_kpi(users, world):
    late = mktask(users["rahbar"], world, title="Kechikkan", assignee_id=users["ishchi"].id,
                  reviewer_id=users["qc"].id, planned_start=D(-10), planned_end=D(-5))
    over = users["rahbar"].get("/tasks", params={"overdue": True}).json()
    assert any(x["id"] == late["id"] for x in over["items"])
    assert next(x for x in over["items"] if x["id"] == late["id"])["overdue_days"] == 5
    blk = users["rahbar"].get("/tasks", params={"blocked": True}).json()
    assert all(x["status"] == "blocked" for x in blk["items"])
    s = users["rahbar"].get("/reports/summary").json()
    assert s["kpi"]["overdue"] >= 1
    assert s["kpi"]["total"] >= 1
    assert isinstance(s["staff"], list) and s["staff"]
    assert len(s["daily_done"]) == 14


# ---------------------------------------------------------------- §13.12 optimistic lock
def test_12_version_conflict(users, world):
    t = mktask(users["rahbar"], world, assignee_id=users["ishchi"].id, reviewer_id=users["qc"].id)
    v = t["row_version"]
    assert users["rahbar"].patch(f"/tasks/{t['id']}", {"row_version": v, "title": "Birinchi"}).status_code == 200
    r = users["rahbar"].patch(f"/tasks/{t['id']}", {"row_version": v, "title": "Ikkinchi"})
    assert r.status_code == 409 and r.json()["code"] == "VERSION_CONFLICT"


def test_12b_date_change_requires_reason(users, world):
    t = mktask(users["rahbar"], world, assignee_id=users["ishchi"].id, reviewer_id=users["qc"].id)
    r = users["rahbar"].patch(f"/tasks/{t['id']}", {"row_version": t["row_version"], "planned_end": D(9)})
    assert r.status_code == 422
    r = users["rahbar"].patch(f"/tasks/{t['id']}", {"row_version": t["row_version"], "planned_end": D(9),
                                                   "date_change_reason": "Material kechikdi"})
    assert r.status_code == 200 and r.json()["planned_end"] == D(9)
    h = users["rahbar"].get(f"/tasks/{t['id']}/history").json()
    assert any(x["action"] == "update" and "planned_end" in x["new_values_json"] for x in h)


# ---------------------------------------------------------------- §13.13 audit with source
def test_13_audit_records_source_and_actor(users, world, client):
    t = mktask(users["rahbar"], world, assignee_id=users["ishchi"].id, reviewer_id=users["qc"].id)
    # act as the bot (service token) on behalf of the assignee
    r = client.post(f"/tasks/{t['id']}/start", json={},
                    headers={"X-Service-Token": "test-service", "X-Acting-User-Id": str(users["ishchi"].id), "X-Source": "bot"})
    assert r.status_code == 200, r.text
    h = users["rahbar"].get(f"/tasks/{t['id']}/history").json()
    start = next(x for x in h if x["action"] == "start")
    assert start["source"] == "bot"
    assert start["actor_name"] == "Rustam Ergashev"
    assert start["request_id"]


# ---------------------------------------------------------------- §13.19 bulk copy
def test_19_bulk_copy_dry_run_then_create(users, world):
    src = world["floors"][0]["id"]
    a = mktask(users["rahbar"], world, title="Qavat ishi 1", location_id=src,
               assignee_id=users["ishchi"].id, reviewer_id=users["qc"].id)
    mktask(users["rahbar"], world, title="Qavat ishi 2", location_id=src,
           assignee_id=users["ishchi"].id, reviewer_id=users["qc"].id, depends_on=[a["id"]])
    tgts = [f["id"] for f in world["floors"][1:3]]
    body = {"source_location_id": src, "target_location_ids": tgts, "date_step_days": 2,
            "assignee_policy": "keep", "dependency_policy": "chain", "as_draft": True, "dry_run": True}
    prev = users["rahbar"].post("/tasks/bulk-copy", json=body)
    assert prev.status_code == 200, prev.text
    p = prev.json()
    assert p["dry_run"] is True and p["total"] == len(p["items"]) > 0
    run = users["rahbar"].post("/tasks/bulk-copy", json={**body, "dry_run": False})
    assert run.status_code == 200
    assert len(run.json()["created"]) == p["total"]
    made = users["rahbar"].get("/tasks", params={"location_id": tgts[0], "limit": 200}).json()
    assert made["total"] >= 1
    job = users["rahbar"].get(f"/jobs/{run.json()['job_id']}").json()
    assert job["status"] == "done" and job["done"] == job["total"]


# ---------------------------------------------------------------- §13.21 blocking a user
def test_21_blocked_user_keeps_tasks_and_review_queue_moves(admin, users, world, client):
    t = mktask(users["rahbar"], world, assignee_id=users["ishchi"].id, reviewer_id=users["qc"].id)
    users["ishchi"].post(f"/tasks/{t['id']}/start")
    ready_for_review(users["ishchi"], t)
    assert users["ishchi"].post(f"/tasks/{t['id']}/submit-review").status_code == 200
    r = admin.post(f"/users/{users['qc'].id}/block")
    assert r.status_code == 200 and r.json()["is_active"] is False
    after = admin.get(f"/tasks/{t['id']}").json()
    assert after["is_active"] if "is_active" in after else True
    assert after["reviewer_id"] != users["qc"].id
    assert client.post("/auth/login", json={"login": "qc", "password": "parol1234567"}).status_code == 401
    admin.post(f"/users/{users['qc'].id}/unblock")
    assert client.post("/auth/login", json={"login": "qc", "password": "parol1234567"}).status_code == 200


# ---------------------------------------------------------------- §13.22 archive work type
def test_22_task_type_archived_not_deleted(admin, world):
    tt = admin.post("/task-types", json={"name": "Vaqtinchalik tur", "default_duration_days": 2,
                                         "required_evidence_kinds": ["after"], "default_checklist_json": []}).json()
    r = admin.patch(f"/task-types/{tt['id']}", {"is_active": False})
    assert r.status_code == 200 and r.json()["is_active"] is False
    assert not any(x["id"] == tt["id"] for x in admin.get("/task-types").json())
    assert any(x["id"] == tt["id"] for x in admin.get("/task-types", params={"include_inactive": True}).json())


# ---------------------------------------------------------------- §13.23 CSV
def test_23_csv_export(users):
    r = users["rahbar"].get("/reports/export.csv", params={"lang": "uz"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    body = r.content.decode("utf-8")
    assert body.startswith("﻿")
    head = body.splitlines()[0]
    assert head.count(";") >= 20 and "Kod" in head
    ru = users["rahbar"].get("/reports/export.csv", params={"lang": "ru"}).content.decode("utf-8")
    assert "Код" in ru.splitlines()[0]


# ---------------------------------------------------------------- permissions & scope
def test_scope_project_and_location(users, world, admin):
    t = mktask(users["rahbar"], world, assignee_id=users["ishchi"].id, reviewer_id=users["qc"].id)
    # a prorab of another block cannot read it
    r = users["chet"].get(f"/tasks/{t['id']}")
    assert r.status_code == 403 and r.json()["code"] == "SCOPE_FORBIDDEN"
    # ...and it is not in his list either
    assert not any(x["id"] == t["id"] for x in users["chet"].get("/tasks", params={"limit": 200}).json()["items"])
    # observer can read but not create
    assert users["kuzat"].get(f"/tasks/{t['id']}").status_code == 200
    r = users["kuzat"].post("/tasks", json={"project_id": world["project"]["id"], "type_id": world["umumiy"]["id"],
                                            "title": "Kuzatuvchi vazifa", "assignee_id": users["ishchi"].id, "reviewer_id": users["qc"].id,
                                            "planned_start": D(0), "planned_end": D(1)})
    assert r.status_code == 403 and r.json()["code"] == "PERMISSION_DENIED"
    assert users["kuzat"].get("/reports/export.csv").status_code == 403


def test_assignee_only_sees_own_tasks(users, world):
    mine = mktask(users["rahbar"], world, assignee_id=users["ishchi"].id, reviewer_id=users["qc"].id)
    other = mktask(users["rahbar"], world, assignee_id=users["ishchi2"].id, reviewer_id=users["qc"].id)
    lst = users["ishchi"].get("/tasks", params={"limit": 200}).json()["items"]
    ids = {x["id"] for x in lst}
    assert mine["id"] in ids and other["id"] not in ids
    assert users["ishchi"].get(f"/tasks/{other['id']}").status_code == 403
    assert users["ishchi"].post(f"/tasks/{other['id']}/start").status_code == 403


def test_permissions_object_drives_ui(users, world):
    t = mktask(users["rahbar"], world, assignee_id=users["ishchi"].id, reviewer_id=users["qc"].id)
    p = users["ishchi"].get(f"/tasks/{t['id']}").json()["permissions"]
    assert p["start"] and not p["accept"] and not p["assign"] and not p["change_dates"]
    p2 = users["qc"].get(f"/tasks/{t['id']}").json()["permissions"]
    assert not p2["start"] and not p2["accept"]  # not in review yet
    p3 = users["kuzat"].get(f"/tasks/{t['id']}").json()["permissions"]
    assert not any([p3["start"], p3["edit"], p3["comment"], p3["upload"]])


def test_invalid_transition(users, world):
    t = mktask(users["rahbar"], world, assignee_id=users["ishchi"].id, reviewer_id=users["qc"].id)
    r = users["rahbar"].post(f"/tasks/{t['id']}/transition", json={"to": "done"})
    assert r.status_code == 422 and r.json()["code"] == "INVALID_TRANSITION"


def test_done_task_is_locked_then_reopen(users, world):
    t = mktask(users["rahbar"], world, assignee_id=users["ishchi"].id, reviewer_id=users["qc"].id)
    users["ishchi"].post(f"/tasks/{t['id']}/start")
    ready_for_review(users["ishchi"], t)
    assert users["ishchi"].post(f"/tasks/{t['id']}/submit-review").status_code == 200
    acc = users["qc"].post(f"/tasks/{t['id']}/accept")
    assert acc.status_code == 200, acc.text
    d = acc.json()
    late = users["ishchi"].upload(f"/tasks/{t['id']}/attachments",
                                  files={"file": ("a.png", PNG, "image/png")}, data={"kind": "after"})
    assert late.status_code == 422 and late.json()["code"] == "INVALID_TRANSITION"
    assert users["rahbar"].patch(f"/tasks/{t['id']}", {"row_version": d["row_version"], "title": "x"}).status_code == 422
    assert users["rahbar"].delete(f"/tasks/{t['id']}").status_code == 422
    r = users["rahbar"].post(f"/tasks/{t['id']}/reopen", json={"to": "progress", "note": "Qayta"})
    assert r.status_code == 200 and r.json()["status"] == "progress" and r.json()["actual_end"] is None


def test_file_validation_and_signed_url(users, world, client):
    t = mktask(users["rahbar"], world, assignee_id=users["ishchi"].id, reviewer_id=users["qc"].id)
    bad = users["ishchi"].upload(f"/tasks/{t['id']}/attachments",
                                 files={"file": ("a.exe", b"MZ", "application/x-msdownload")}, data={"kind": "during"})
    assert bad.status_code == 415 and bad.json()["code"] == "FILE_TYPE_NOT_ALLOWED"
    ok = users["ishchi"].upload(f"/tasks/{t['id']}/attachments",
                                files={"file": ("a.png", PNG, "image/png")}, data={"kind": "during"}).json()
    url = ok["url"]
    path = url.split("/files/")[1]
    assert client.get(f"/files/{path}").status_code == 200
    assert client.get(f"/files/{ok['id']}?exp=1&sig=bad").status_code == 401


def test_comments_and_mentions(users, world):
    t = mktask(users["rahbar"], world, assignee_id=users["ishchi"].id, reviewer_id=users["qc"].id)
    r = users["rahbar"].post(f"/tasks/{t['id']}/comments", json={"text": "@ishchi bugun boshlang"})
    assert r.status_code == 201 and r.json()["mentions_json"] == [users["ishchi"].id]
    assert any(n["event"] == "mentioned" for n in users["ishchi"].get("/notifications").json())
    assert len(users["ishchi"].get(f"/tasks/{t['id']}/comments").json()) == 1


def test_soft_delete_hides_task(users, world):
    t = mktask(users["rahbar"], world, assignee_id=users["ishchi"].id, reviewer_id=users["qc"].id)
    assert users["rahbar"].delete(f"/tasks/{t['id']}").status_code == 204
    assert users["rahbar"].get(f"/tasks/{t['id']}").status_code == 404
    assert not any(x["id"] == t["id"] for x in users["rahbar"].get("/tasks", params={"limit": 200}).json()["items"])


def test_templates_instantiate(admin, users, world):
    tpl = admin.get("/task-templates").json()[0]
    r = users["rahbar"].post(f"/task-templates/{tpl['id']}/instantiate", json={
        "project_id": world["project"]["id"], "location_id": world["floors"][0]["id"],
        "assignee_id": users["ishchi"].id, "reviewer_id": users["qc"].id, "planned_start": D(0), "variables": {}})
    assert r.status_code == 201, r.text
    assert world["floors"][0]["name"] in r.json()["title"]
    assert r.json()["checklist_total"] > 0


def test_telegram_link_flow(client, users, admin):
    code = users["ishchi"].post("/telegram/link-code").json()
    assert len(code["code"]) == 6
    svc = {"X-Service-Token": "test-service"}
    r = client.post("/telegram/consume-code", json={"code": code["code"], "telegram_user_id": 555001}, headers=svc)
    assert r.status_code == 200 and r.json()["telegram_user_id"] == 555001
    # one telegram account -> one user
    code2 = users["ishchi2"].post("/telegram/link-code").json()
    r = client.post("/telegram/consume-code", json={"code": code2["code"], "telegram_user_id": 555001}, headers=svc)
    assert r.status_code == 422 and r.json()["code"] == "TELEGRAM_ALREADY_LINKED"
    # code is single-use
    r = client.post("/telegram/consume-code", json={"code": code["code"], "telegram_user_id": 555002}, headers=svc)
    assert r.status_code == 422
    assert client.get("/telegram/user-by-tg/555001", headers=svc).json()["login"] == "ishchi"
    assert client.get("/telegram/user-by-tg/999999", headers=svc).status_code == 404
    assert client.get("/telegram/outbox", headers=svc).status_code == 200
    assert client.get("/telegram/outbox").status_code == 401


def test_bot_outbox_delivers_pending_telegram_notifications(client, users, world):
    """ishchi is linked (previous test) -> new assignment queues a telegram notification."""
    svc = {"X-Service-Token": "test-service"}
    t = mktask(users["rahbar"], world, title="Bot uchun", assignee_id=users["ishchi"].id, reviewer_id=users["qc"].id)
    out = client.get("/telegram/outbox", headers=svc).json()
    mine = [o for o in out if o["task_id"] == t["id"]]
    assert mine and mine[0]["telegram_user_id"] == 555001
    assert mine[0]["event"] == "assigned"
    assert mine[0]["payload"]["code"] == t["code"]
    r = client.post("/telegram/outbox/ack", json={"sent": [mine[0]["id"]], "failed": []}, headers=svc)
    assert r.status_code == 200
    again = client.get("/telegram/outbox", headers=svc).json()
    assert not [o for o in again if o["id"] == mine[0]["id"]]


def test_ai_voice_disabled_without_key(users):
    r = users["rahbar"].post("/ai/parse-task", json={"text": "Rustamga 3 kunda devor terish", "lang": "uz"})
    assert r.status_code == 503 and r.json()["code"] == "VOICE_NOT_CONFIGURED"


def test_assignee_fuzzy_matching_unit():
    from app.services.ai import _norm
    from rapidfuzz import fuzz
    assert fuzz.token_set_ratio(_norm("Rustam Erkashev"), _norm("Rustam Ergashev")) > 85
    assert fuzz.token_set_ratio(_norm("Рустам Эргашев"), _norm("Рустам Ергашев")) > 85
    assert fuzz.token_set_ratio(_norm("Sardor"), _norm("Rustam Ergashev")) < 60


def test_weak_password_rejected(admin, world):
    r = admin.post("/users", json={"full_name": "X", "login": "weak1", "password": "12345",
                                   "role_id": world["roles"]["bajaruvchi"], "scope_type": "system"})
    assert r.status_code == 422 and r.json()["code"] == "WEAK_PASSWORD"


def test_role_permission_edit(admin, world):
    role = next(r for r in admin.get("/roles").json() if r["code"] == "kuzatuvchi")
    r = admin.patch(f"/roles/{role['id']}", {"permissions_json": role["permissions_json"] + ["tasks.export"]})
    assert r.status_code == 200 and "tasks.export" in r.json()["permissions_json"]
    admin.patch(f"/roles/{role['id']}", {"permissions_json": role["permissions_json"]})
    adm = next(r for r in admin.get("/roles").json() if r["code"] == "admin")
    assert admin.patch(f"/roles/{adm['id']}", {"permissions_json": []}).status_code == 422
    assert admin.patch(f"/roles/{role['id']}", {"permissions_json": ["nope.nope"]}).status_code == 422


def test_notifications_read(users):
    n = users["ishchi"].get("/notifications").json()
    assert n
    before = users["ishchi"].get("/notifications/unread-count").json()["count"]
    assert before > 0
    users["ishchi"].post("/notifications/read", json={})
    assert users["ishchi"].get("/notifications/unread-count").json()["count"] == 0


# ---------------------------------------------------------------- administration
def test_superadmin_can_create_a_second_full_admin(client, admin, world):
    """Loyiha egasi (admin) yangi to'liq adminni qo'sha oladi va u ham hamma narsani qila oladi."""
    r = admin.post("/users", json={"full_name": "Ikkinchi Admin", "login": "admin2", "password": "AdminIkki2026!",
                                   "role_id": world["roles"]["admin"], "scope_type": "system"})
    assert r.status_code == 201, r.text
    a2 = U(client, "admin2", "AdminIkki2026!")
    assert a2.role == "admin"
    assert {"admin.users", "admin.roles", "admin.projects", "admin.task_types",
            "admin.templates", "tasks.delete", "tasks.reopen"} <= set(a2.perms)

    # the new admin can do the whole administration set
    made = a2.post("/users", json={"full_name": "Yangi Xodim", "login": "yangixodim", "password": "parol1234567",
                                   "role_id": world["roles"]["prorab"], "scope_type": "location",
                                   "scope_id": world["block"]["id"]})
    assert made.status_code == 201
    assert a2.post(f"/users/{made.json()['id']}/block").json()["is_active"] is False
    assert a2.post(f"/users/{made.json()['id']}/unblock").json()["is_active"] is True
    assert a2.post("/projects", json={"code": "SAFF-03", "name": "Uchinchi obyekt"}).status_code == 201
    assert a2.post("/task-types", json={"name": "A2 turi", "default_duration_days": 2,
                                        "required_evidence_kinds": [], "default_checklist_json": []}).status_code == 201
    kuz = next(x for x in a2.get("/roles").json() if x["code"] == "kuzatuvchi")
    assert a2.patch(f"/roles/{kuz['id']}", {"permissions_json": kuz["permissions_json"]}).status_code == 200
    assert a2.get("/reports/summary").status_code == 200
    # sees every project, not just one
    assert len(a2.get("/projects").json()) >= 2


def test_non_admin_cannot_touch_administration(users):
    for who in ("rahbar", "prorab", "ishchi", "qc", "kuzat"):
        u = users[who]
        assert u.post("/users", json={"full_name": "X", "login": f"x{who}", "password": "parol1234567",
                                      "role_id": 1, "scope_type": "system"}).status_code == 403
        assert u.post("/projects", json={"code": "ZZ", "name": "Z"}).status_code == 403
        assert u.post("/task-types", json={"name": "Z"}).status_code == 403
        assert u.get("/roles/permissions").status_code == 200        # ro'yxatni ko'rish mumkin
        assert u.patch("/roles/1", {"permissions_json": []}).status_code == 403


def test_each_role_sees_its_own_panel(users, admin):
    """Har rol uchun /auth/me dagi ruxsatlar - UI yon menyusi shunga qarab chiziladi."""
    expect = {
        "rahbar":       {"has": ["tasks.create", "tasks.bulk_create", "reports.read", "tasks.export", "admin.templates"],
                         "hasnt": ["admin.users", "admin.roles", "admin.task_types", "admin.projects"]},
        "prorab":       {"has": ["tasks.create", "tasks.start", "progress.create", "reports.read", "tasks.export"],
                         "hasnt": ["tasks.bulk_create", "tasks.accept", "tasks.change_dates", "admin.users"]},
        "ishchi":       {"has": ["tasks.read", "tasks.start", "tasks.submit_review", "checklist.edit", "progress.create", "attachments.upload"],
                         "hasnt": ["tasks.create", "tasks.accept", "reports.read", "tasks.export", "admin.users"]},
        "qc":           {"has": ["tasks.read", "tasks.accept", "tasks.return", "reports.read", "tasks.export"],
                         "hasnt": ["tasks.create", "tasks.start", "progress.create", "admin.users"]},
        "kuzat":        {"has": ["tasks.read", "reports.read"],
                         "hasnt": ["tasks.create", "tasks.start", "tasks.accept", "tasks.export", "comments.create"]},
    }
    for who, e in expect.items():
        perms = set(users[who].perms)
        for p in e["has"]:
            assert p in perms, f"{who} must have {p}"
        for p in e["hasnt"]:
            assert p not in perms, f"{who} must NOT have {p}"
    assert set(admin.perms) >= set().union(*[set(v["has"]) | set(v["hasnt"]) for v in expect.values()])
