"""Ovoz bilan vazifa berish: ism topish va tekshiruvchini tanlash.

OPENAI_API_KEY kerak bo'lgan qismlar (ovoz->matn, matn->JSON) bu yerda sinalmaydi -
ular tashqi xizmat. Bu yerda kalitsiz ham ishlaydigan, eng ko'p xato chiqaradigan
qism sinaladi: eshitilgan ismni xodimga moslashtirish.
"""
from datetime import date, timedelta

from app.db import SessionLocal
from app.models import User
from app.services import ai
from sqlalchemy import select


def _db():
    return SessionLocal()


def test_uzbek_spelling_differences_still_find_the_person(users, world):
    """«Rustam Erkashev» deb eshitilsa ham «Rustam Ergashev» topilishi kerak."""
    db = _db()
    try:
        creator = db.scalar(select(User).where(User.login == "rahbar"))
        for heard in ("Rustam Erkashev", "rustam ergashov", "Rustamga", "Ergashev Rustam"):
            cands, confident = ai.match_users(db, heard, world["project"]["id"], creator)
            assert cands, f"«{heard}» uchun hech kim topilmadi"
            assert cands[0].full_name == "Rustam Ergashev", f"«{heard}» -> {cands[0].full_name}"
    finally:
        db.close()


def test_two_people_with_the_same_name_are_never_auto_picked(admin, users, world, client):
    """Ikkita bir xil ism bo'lsa bot/web o'zi tanlamaydi - tugma chiqaradi, va tugmalar
    bir-biridan ajralib turishi kerak (rol va joy bilan)."""
    twin = admin.post("/users", json={
        "full_name": "Rustam Ergashev", "login": "rergashev2", "password": "1234",
        "role_id": world["roles"]["bajaruvchi"], "scope_type": "project",
        "scope_id": world["project"]["id"]}).json()
    assert twin["id"]

    db = _db()
    try:
        creator = db.scalar(select(User).where(User.login == "rahbar"))
        cands, confident = ai.match_users(db, "Rustam Ergashev", world["project"]["id"], creator)
        names = [c.full_name for c in cands]
        assert names.count("Rustam Ergashev") == 2, f"ikkala odam ham chiqishi kerak: {names}"
        assert confident is False, "bir xil ism - avtomatik tanlanmasligi kerak"
        # tugmalar ajralib turadimi
        labels = [f"{c.full_name} {c.hint}" for c in cands]
        assert len(labels) == len(set(labels)), f"tugmalar bir xil ko'rinadi: {labels}"
        assert all(c.hint for c in cands), "hint bo'sh - kimligini ajratib bo'lmaydi"
    finally:
        db.close()
    admin.post(f"/users/{twin['id']}/block")


def test_voice_never_offers_someone_who_cannot_do_the_work(users, world):
    """Tekshiruvchi/kuzatuvchi nomi aytilsa ham ular bajaruvchi sifatida taklif qilinmaydi -
    aks holda vazifa yaratishda server rad etardi (cannot_execute)."""
    db = _db()
    try:
        creator = db.scalar(select(User).where(User.login == "rahbar"))
        for heard in ("Doniyor Toshmatov", "Kuzatuvchi K"):
            cands, _ = ai.match_users(db, heard, world["project"]["id"], creator)
            assert not any(c.full_name == heard for c in cands), f"{heard} taklif qilinmasligi kerak"
    finally:
        db.close()


def test_default_reviewer_can_always_accept(users, world):
    """Avtomatik tanlangan tekshiruvchi haqiqatan qabul qila olishi kerak."""
    db = _db()
    try:
        for login in ("rahbar", "prorab"):
            creator = db.scalar(select(User).where(User.login == login))
            worker = db.scalar(select(User).where(User.login == "ishchi"))
            rid = ai.default_reviewer_id(db, world["project"]["id"], worker.id, creator)
            assert rid, f"{login} uchun tekshiruvchi topilmadi"
            rev = db.get(User, rid)
            assert "tasks.accept" in (rev.role.permissions_json or []), \
                f"{login} uchun tanlangan {rev.full_name} ({rev.role.code}) qabul qila olmaydi"
            assert rid != worker.id, "bajaruvchining o'zi tekshiruvchi bo'lib qoldi"
    finally:
        db.close()


def test_parsed_task_can_actually_be_created(users, world, client):
    """Ovozdan chiqqan ma'lumot bilan vazifa yaratilganda server uni qabul qilishi kerak -
    ya'ni tanlangan bajaruvchi ham, tekshiruvchi ham qoidaga mos."""
    db = _db()
    try:
        creator = db.scalar(select(User).where(User.login == "rahbar"))
        cands, _ = ai.match_users(db, "Rustam Ergashev", world["project"]["id"], creator)
        assignee_id = cands[0].id
        reviewer_id = ai.default_reviewer_id(db, world["project"]["id"], assignee_id, creator)
    finally:
        db.close()
    r = users["rahbar"].post("/tasks", json={
        "project_id": world["project"]["id"], "location_id": world["floors"][0]["id"],
        "type_id": world["umumiy"]["id"], "title": "Ovozdan berilgan vazifa",
        "assignee_id": assignee_id, "reviewer_id": reviewer_id,
        "planned_start": str(date.today()), "planned_end": str(date.today() + timedelta(days=3))})
    assert r.status_code == 201, r.text
