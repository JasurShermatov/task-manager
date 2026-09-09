"""Eslatma dvigateli — muddat yaqinlashgan sari tez-tez eslatadi, tunda jim turadi."""
from datetime import datetime, timedelta

import pytest

from app import clock
from app.db import SessionLocal
from app.models import MANAGERS, NEW, PROGRESS, SUBMITTED, Notification, Task, User
from app.services import reminders as rem
from sqlalchemy import select


def _task(due_at: datetime, status=NEW) -> Task:
    return Task(id=1, code="V-1001", title="Sinov", assignee_id=1, created_by=2,
                due_at=due_at, status=status)


def test_reminder_count_grows_as_the_deadline_approaches():
    """Talab: 1 kunlik dedlayn -> kuniga 3 marta; uzoqroq bo'lsa kamroq."""
    day = datetime(2026, 9, 9)
    ref = clock.at(day.date(), 20)          # kun oxiri - shu kungi hamma slot o'tgan
    counts = {}
    for days_left in (7, 3, 1, 0, -1):
        t = _task(clock.at((day + timedelta(days=days_left)).date(), 18))
        counts[days_left] = len(rem.slots_for(t, ref))
    assert counts[7] == 1, "uzoq muddat - kuniga bir marta yetadi"
    assert counts[3] == 2
    assert counts[1] == 2
    assert counts[0] == 3, "bugun tugaydigan vazifa kuniga uch marta eslatilishi kerak"
    assert counts[-1] == 3, "kechikkanda ham uch marta"


def test_only_slots_that_already_passed_are_sent():
    day = datetime(2026, 9, 9).date()
    t = _task(clock.at(day, 18))
    assert rem.slots_for(t, clock.at(day, 8, 30)) == [], "09:00 dan oldin hech narsa yuborilmaydi"
    assert len(rem.slots_for(t, clock.at(day, 10))) == 1
    assert len(rem.slots_for(t, clock.at(day, 14))) == 2
    assert len(rem.slots_for(t, clock.at(day, 17))) == 3   # 09, 13 va muddatdan 2 soat oldin


def test_night_is_quiet():
    assert rem.is_quiet(datetime(2026, 9, 9, 22, 0))
    assert rem.is_quiet(datetime(2026, 9, 9, 3, 0))
    assert rem.is_quiet(datetime(2026, 9, 9, 7, 59))
    assert not rem.is_quiet(datetime(2026, 9, 9, 9, 0))
    assert not rem.is_quiet(datetime(2026, 9, 9, 20, 59))
    # tunga to'g'ri kelgan slot yuborilmaydi
    day = datetime(2026, 9, 10).date()
    t = _task(clock.at(day, 7))              # muddat ertalab 07:00 -> "2 soat oldin" = 05:00
    assert all(not rem.is_quiet(s) for s in rem.slots_for(t, clock.at(day, 20)))


def test_reminder_hours_come_from_settings():
    t = _task(clock.at(datetime(2026, 9, 9).date(), 18))
    slots = rem.slots_for(t, clock.at(datetime(2026, 9, 9).date(), 20), hours=(8, 12, 16))
    assert [s.hour for s in slots][:2] == [8, 12]


# ---------------------------------------------------------------- jonli baza ustida
@pytest.fixture
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def _clear(db):
    for n in db.scalars(select(Notification).where(Notification.event.in_(
            ("reminder", "overdue_alert", "overdue_digest", "due_today")))):
        db.delete(n)
    db.commit()


def test_engine_is_idempotent(boss, users, world, db):
    """Scheduler har 5 daqiqada ishlaydi — ikkinchi chaqiruv takror xabar yozmasligi kerak."""
    _clear(db)
    w = world["users"]["worker1"]["id"]
    r = boss.post("/tasks", json={"title": "Eslatma sinovi", "assignee_id": w,
                                  "due_at": (clock.today() - timedelta(days=1)).isoformat()})
    assert r.status_code == 201, r.text
    # Botga ulanmagan odamga xabar yozilmaydi — shuning uchun ijrochiga ham,
    # boshqaruvchilarga ham telegram id qo'yamiz.
    linked = []
    user = db.get(User, w)
    user.telegram_user_id = 555001
    linked.append(user)
    for i, m in enumerate(db.scalars(select(User).where(User.role.in_(MANAGERS))), start=2):
        m.telegram_user_id = 555000 + i
        linked.append(m)
    db.commit()

    ref = clock.at(clock.today(), 17, 5)
    first = rem.run_reminders(db, ref)
    second = rem.run_reminders(db, ref)
    assert first["assignee"] >= 1, first
    assert first["late_alert"] >= 1, "boss va assistantga kechikish xabari borishi kerak"
    assert first["digest"] >= 1, "kunlik kechikkanlar ro'yxati borishi kerak"
    assert second == {"assignee": 0, "late_alert": 0, "digest": 0}, "takroriy xabar yozildi"

    events = [n.event for n in db.scalars(select(Notification).where(Notification.task_id == r.json()["id"]))]
    assert "reminder" in events and "overdue_alert" in events
    for u in linked:
        u.telegram_user_id = None
    db.commit()


def test_people_without_telegram_get_no_queued_messages(boss, world, db):
    """Botga ulanmagan odamga xabar yozilsa, navbatda «failed» bo'lib chiqindi qolardi."""
    _clear(db)
    w = world["users"]["worker1"]["id"]
    boss.post("/tasks", json={"title": "Ulanmagan odam", "assignee_id": w,
                              "due_at": (clock.today() - timedelta(days=2)).isoformat()})
    assert all(u.telegram_user_id is None for u in db.scalars(select(User))), "sinov sharti"
    assert rem.run_reminders(db, clock.at(clock.today(), 17, 5)) == \
        {"assignee": 0, "late_alert": 0, "digest": 0}


def test_no_reminders_at_night(boss, world, db):
    _clear(db)
    assert rem.run_reminders(db, clock.at(clock.today(), 23, 30)) == \
        {"assignee": 0, "late_alert": 0, "digest": 0}


def test_submitted_task_stops_reminding(boss, users, world, db):
    _clear(db)
    w = world["users"]["worker2"]["id"]
    t = boss.post("/tasks", json={"title": "Topshirilgach jim", "assignee_id": w,
                                  "due_at": (clock.today() - timedelta(days=1)).isoformat()}).json()
    users["worker2"].prove(t["id"])
    users["worker2"].post(f"/tasks/{t['id']}/submit", {"note": "Tayyor"})
    rem.run_reminders(db, clock.at(clock.today(), 17, 5))
    sent = db.scalars(select(Notification).where(Notification.task_id == t["id"],
                                                 Notification.event == "reminder")).all()
    assert not sent, "topshirilgan vazifa bo'yicha eslatma yuborilmasligi kerak"
