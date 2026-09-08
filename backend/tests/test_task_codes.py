"""Vazifa kodi (V-1234) hech qachon takrorlanmasligi kerak.

Nima bo'lgan edi: faker (ilgari demo_data) satrlarni bazaga to'g'ridan-to'g'ri yozadi va
Postgres'dagi `task_code_seq` ketma-ketligi joyida qoladi. Keyin foydalanuvchi web/botdan
yangi vazifa yaratganda nextval allaqachon band bo'lgan kodni qaytaradi ->
UNIQUE buzilishi -> 500 "Server xatosi". Testlar SQLite'da ishlagani uchun buni ko'rmagan.

Endi ikki qavat himoya bor:
  1. ilova ko'tarilganda ketma-ketlik eng katta koddan keyinga suriladi (main.py)
  2. next_code() band kodga duch kelsa o'zini o'zi tuzatadi (services/tasks.py)

Bu yerdagi testlar dialektdan qat'i nazar ishlaydigan qismni qo'riqlaydi.
"""
from datetime import date, timedelta

from sqlalchemy import select
from conftest import U  # noqa: F401

D = lambda n: str(date.today() + timedelta(days=n))


def test_codes_stay_unique_when_rows_were_inserted_outside_the_api(admin, users, world, client):
    """Bazaga tashqaridan (faker kabi) yozilgan kodlardan keyin ham yangi vazifa yaratiladi."""
    from app.db import SessionLocal
    from app.models import Task
    from app.services import tasks as svc

    db = SessionLocal()
    try:
        # faker qiladigan ish: keyingi 30 ta kodni oldindan band qilib qo'yamiz
        top = svc.max_code_num(db)
        sample = db.scalars(select(Task).limit(1)).first()
        assert sample is not None, "sinov uchun bazada vazifa bo'lishi kerak"
        for i in range(1, 31):
            db.add(Task(code=f"V-{top + i}", project_id=sample.project_id, type_id=sample.type_id,
                        title=f"Tashqaridan yozilgan {i}", status="plan", priority="normal",
                        assignee_id=sample.assignee_id, reviewer_id=sample.reviewer_id,
                        planned_start=date.today(), planned_end=date.today() + timedelta(days=2),
                        created_by=sample.created_by))
        db.commit()
        svc.sync_code_sequence(db)   # ilova ko'tarilganda / faker oxirida bo'ladigan ish
        db.commit()
    finally:
        db.close()

    # endi API orqali ketma-ket 5 ta vazifa yaratamiz - hech biri to'qnashmasligi kerak
    codes = []
    for i in range(5):
        r = users["rahbar"].post("/tasks", json={
            "project_id": world["project"]["id"], "location_id": world["floors"][0]["id"],
            "type_id": world["umumiy"]["id"], "title": f"Ketma-ketlikdan keyin {i}",
            "assignee_id": users["ishchi"].id, "reviewer_id": users["qc"].id,
            "planned_start": D(0), "planned_end": D(3)})
        assert r.status_code == 201, r.text          # ilgari shu yerda 500 chiqardi
        codes.append(r.json()["code"])
    assert len(set(codes)) == len(codes), f"kod takrorlandi: {codes}"

    # butun bazada ham takror yo'q
    db = SessionLocal()
    try:
        all_codes = [c for (c,) in db.execute(select(Task.code))]
    finally:
        db.close()
    assert len(all_codes) == len(set(all_codes)), "bazada takrorlangan kod bor"


def test_max_code_num_ignores_foreign_codes(admin):
    """Chetdan kelgan g'alati kodlar (ESKI-77, V-XX) hisoblashni buzmasligi kerak."""
    from app.db import SessionLocal
    from app.services import tasks as svc
    db = SessionLocal()
    try:
        assert svc.max_code_num(db) > 0
    finally:
        db.close()


def test_sync_is_a_no_op_outside_postgres(admin):
    """SQLite'da ketma-ketlik yo'q - funksiya jim qaytadi, xato bermaydi."""
    from app.db import SessionLocal
    from app.services import tasks as svc
    db = SessionLocal()
    try:
        assert svc.sync_code_sequence(db) == 0
    finally:
        db.close()
