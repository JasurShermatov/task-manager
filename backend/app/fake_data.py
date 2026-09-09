"""Sinov ma'lumoti: bitta boss, assistant, 10 bo'lim boshlig'i va asosiy bo'limda ~50 xodim,
ular ustida bir necha oylik vazifa tarixi — hisobot va foizlarni darhol ko'rish uchun.

    python -m app.fake_data            # bo'sh bazani to'ldiradi
    python -m app.fake_data --reset    # tozalab, qaytadan to'ldiradi
    python -m app.fake_data --wipe     # faqat tozalaydi (boss qoladi)

Hamma parol: 1234
"""
from __future__ import annotations

import argparse
import random
import sys
from datetime import timedelta

from sqlalchemy import delete, func, select

from . import clock
from .auth import hash_password
from .db import SessionLocal
from .models import (
    ASSISTANT, BOSS, CANCELLED, DONE, HEAD, NEW, PROGRESS, SUBMITTED, WORKER,
    Department, Notification, RefreshToken, Task, TaskComment, TaskFile, TaskHistory,
    TelegramLinkCode, User,
)
from .seed import seed
from .services import tasks as svc

random.seed(20260909)

DEPARTMENTS = ["Ta'minot", "Qurilish", "Loyihalash", "Moliya", "Transport",
               "Ombor", "Sotuv", "Kadrlar", "Xavfsizlik", "Texnika"]

FIRST = ["Sanjar", "Bekzod", "Anvar", "Dilshod", "Jasur", "Otabek", "Rustam", "Shuhrat", "Aziz",
         "Farrux", "Ulug'bek", "Nodir", "Bahodir", "Sardor", "Javohir", "Doniyor", "Alisher",
         "Umid", "Islom", "Kamol", "Shohruh", "Temur", "Xurshid", "Zafar", "Mirzo"]
LAST = ["Ergashev", "Toshmatov", "Qodirov", "Yusupov", "Rahmonov", "Sobirov", "Xolmatov",
        "Nazarov", "Umarov", "Karimov", "Аbdullayev", "Musayev", "Jalilov", "Saidov", "Tursunov"]
POSITIONS = ["Buxgalter", "Ta'minotchi", "Prorab", "Muhandis", "Haydovchi", "Omborchi",
             "Menejer", "Operator", "Usta", "Hisobchi"]

TASK_TITLES = [
    "Ombor hisobotini tayyorlash", "Materialni obyektga yetkazish", "1-etaj qurilishini tugatish",
    "Smetani qayta hisoblash", "Yetkazib beruvchi bilan shartnoma tuzish", "Texnika holatini tekshirish",
    "Oylik hisobotni topshirish", "Ishchilar ro'yxatini yangilash", "Chizmani kelishib olish",
    "Beton buyurtmasini berish", "Qurilish maydonini tozalash", "Xavfsizlik brifingini o'tkazish",
    "Elektr ta'minotini ulash", "Suv quvurlarini sinovdan o'tkazish", "Fasad panellarini buyurtma qilish",
    "Ish haqi jadvalini tayyorlash", "Yangi ishchilarni rasmiylashtirish", "Transport grafigini tuzish",
    "Ombor qoldig'ini inventarizatsiya qilish", "Subpudratchi ishini qabul qilish",
]
NOTES = ["Bajarildi, hujjatlar tayyor.", "Ish to'liq yakunlandi.", "Materiallar yetkazildi, rasm ilova.",
         "Tekshirildi, muammo yo'q.", "Hisobot tayyor, ilova qilindi."]

TABLES = [TaskHistory, TaskComment, TaskFile, Notification, Task, TelegramLinkCode, RefreshToken]


def wipe(db):
    for model in TABLES:
        db.execute(delete(model))
    db.execute(delete(User).where(User.role != BOSS))
    db.execute(delete(Department))
    db.commit()
    svc.sync_code_sequence(db)


def name(used: set) -> str:
    for _ in range(200):
        n = f"{random.choice(FIRST)} {random.choice(LAST)}"
        if n not in used:
            used.add(n)
            return n
    return f"Xodim {len(used) + 1}"


def make_people(db) -> dict:
    used, logins = set(), set()

    def add(full, role, **kw):
        base = full.split()[0].lower()
        login = base
        i = 1
        while login in logins or db.scalar(select(User).where(User.login == login)):
            i += 1
            login = f"{base}{i}"
        logins.add(login)
        u = User(full_name=full, login=login, password_hash=hash_password("1234"),
                 role=role, lang="uz", **kw)
        db.add(u)
        return u

    boss = db.scalar(select(User).where(User.role == BOSS))
    assistant = add(name(used), ASSISTANT, position="Boshliq yordamchisi")
    db.flush()

    deps, heads = [], []
    for i, dep_name in enumerate(DEPARTMENTS):
        d = Department(name=dep_name, sort_order=i)
        db.add(d)
        db.flush()
        deps.append(d)
        heads.append(add(name(used), HEAD, department_id=d.id, position="Bo'lim boshlig'i"))
    workers = [add(name(used), WORKER, position=random.choice(POSITIONS)) for _ in range(50)]
    db.flush()
    return {"boss": boss, "assistant": assistant, "departments": deps,
            "heads": heads, "workers": workers}


def make_tasks(db, people: dict, months: int = 3) -> int:
    """Har oyda har bir odamga bir necha vazifa — 70% vaqtida, 20% kechikib, 10% bajarilmagan."""
    now = clock.now()
    givers = [people["boss"], people["assistant"]]
    performers = people["heads"] + people["workers"]
    n = 0
    for person in performers:
        count = random.randint(6, 14) if person.role == HEAD else random.randint(2, 8)
        for _ in range(count):
            days_ago = random.randint(0, months * 30)
            created = now - timedelta(days=days_ago, hours=random.randint(0, 8))
            due = created + timedelta(days=random.randint(1, 10), hours=random.randint(0, 6))
            due = due.replace(minute=0, second=0, microsecond=0)
            giver = random.choice(givers)
            t = Task(code=svc.next_code(db), title=random.choice(TASK_TITLES),
                     description=None if random.random() < 0.6 else "Batafsil: shartnoma bo'yicha.",
                     assignee_id=person.id, created_by=giver.id, due_at=due, original_due_at=due,
                     created_at=created, updated_at=created, status=NEW)
            db.add(t)
            db.flush()
            db.add(TaskHistory(task_id=t.id, action="create", actor_id=giver.id,
                               new_values_json={"title": t.title}, created_at=created))
            _advance(db, t, person, giver, now)
            n += 1
    db.commit()
    return n


def _advance(db, t: Task, person: User, giver: User, now):
    """Vazifani hayotiy holatga olib keladi."""
    roll = random.random()
    past_due = t.due_at < now
    if not past_due:
        if roll < 0.4:
            t.status, t.started_at = PROGRESS, t.created_at + timedelta(hours=4)
        return
    if roll < 0.70:                                   # vaqtida bajarilgan
        submitted = t.due_at - timedelta(hours=random.randint(1, 30))
        _finish(db, t, person, giver, submitted, accepted=True)
    elif roll < 0.90:                                 # kechikib bajarilgan
        submitted = t.due_at + timedelta(days=random.randint(1, 7))
        if submitted > now:
            submitted = now - timedelta(hours=2)
        _finish(db, t, person, giver, submitted, accepted=submitted < now - timedelta(hours=1))
    elif roll < 0.96:                                 # bajarilmagan, ochiq qolgan
        t.status = PROGRESS
        t.started_at = t.created_at + timedelta(hours=6)
    else:                                             # bekor qilingan
        t.status, t.cancelled_at = CANCELLED, t.due_at
        db.add(TaskHistory(task_id=t.id, action="cancel", actor_id=giver.id, created_at=t.due_at))


def _finish(db, t: Task, person: User, giver: User, submitted, accepted: bool):
    if random.random() < 0.15:                        # bir marta qaytarilgan
        t.return_count = 1
        t.last_returned_at = submitted - timedelta(hours=6)
        db.add(TaskHistory(task_id=t.id, action="return", actor_id=giver.id,
                           new_values_json={"reason": "Rasm aniq emas, qaytadan yuboring."},
                           created_at=t.last_returned_at))
    t.started_at = t.created_at + timedelta(hours=random.randint(1, 20))
    t.status, t.submitted_at, t.submit_note = SUBMITTED, submitted, random.choice(NOTES)
    db.add(TaskFile(task_id=t.id, kind="proof", storage_key=f"fake/{t.id}.jpg",
                    filename="dalil.jpg", mime_type="image/jpeg", size=180_000,
                    uploaded_by=person.id, source="bot", created_at=submitted))
    db.add(TaskHistory(task_id=t.id, action="submit", actor_id=person.id, created_at=submitted))
    if accepted:
        done = submitted + timedelta(hours=random.randint(1, 20))
        t.status, t.done_at, t.accepted_by = DONE, done, giver.id
        db.add(TaskHistory(task_id=t.id, action="accept", actor_id=giver.id, created_at=done))
    if random.random() < 0.2:
        db.add(TaskComment(task_id=t.id, text="Material kechikib keldi.", author_id=person.id,
                           created_at=submitted - timedelta(hours=2)))


def report(db) -> bool:
    """To'ldirilgandan keyin o'zini tekshiradi — jim buzilgan ma'lumot qolmasin."""
    from .services import reports as rsvc
    counts = {m.__tablename__: db.execute(select(func.count()).select_from(m)).scalar()
              for m in (Department, User, Task, TaskFile, TaskComment, TaskHistory)}
    print("\nJadvallar:")
    for k, v in counts.items():
        print(f"  {k:<16} {v}")

    statuses = dict(db.execute(select(Task.status, func.count()).group_by(Task.status)).all())
    print("\nHolatlar:", ", ".join(f"{k}={v}" for k, v in sorted(statuses.items())))

    a, b = clock.period_range("month")
    rep = rsvc.summary(db, a, b)
    t = rep["totals"]
    print(f"\nShu oy: berilgan={t['given']} vaqtida={t['on_time']} kechikdi={t['late_done']} "
          f"bajarilmadi={t['not_done']} jarayonda={t['in_progress']} foiz={t['percent']}%")

    ok = True

    def check(cond, msg):
        nonlocal ok
        if not cond:
            ok = False
            print(f"  XATO: {msg}")

    check(t["given"] == t["on_time"] + t["late_done"] + t["not_done"] + t["in_progress"],
          "hisobot guruhlari yig'indisi 'berilgan'ga teng emas")
    check(counts["users"] >= 60, "xodimlar soni kam")
    check(counts["departments"] == len(DEPARTMENTS), "bo'limlar soni noto'g'ri")
    heads = db.scalars(select(User).where(User.role == HEAD)).all()
    check(all(h.department_id for h in heads), "bo'limsiz boshliq bor")
    check(len({h.department_id for h in heads}) == len(heads), "bitta bo'limda ikkita boshliq")
    check(not db.scalar(select(User).where(User.role == WORKER, User.department_id.is_not(None))),
          "ijrochiga bo'lim biriktirilgan (asosiy bo'lim xodimida bo'lim bo'lmaydi)")
    submitted = db.scalars(select(Task).where(Task.status.in_((SUBMITTED, DONE)))).all()
    proofs = {f.task_id for f in db.scalars(select(TaskFile).where(TaskFile.kind == "proof"))}
    check(all(t_.id in proofs for t_ in submitted), "dalilsiz topshirilgan vazifa bor")
    check(all(t_.submitted_at for t_ in submitted), "topshirilgan vaqti yo'q vazifa bor")
    check(all(t_.accepted_by for t_ in db.scalars(select(Task).where(Task.status == DONE))),
          "qabul qilgan odam yozilmagan")
    codes = [c for (c,) in db.execute(select(Task.code))]
    check(len(codes) == len(set(codes)), "vazifa kodi takrorlangan")

    print("\nMantiq tekshiruvi:", "HAMMASI TO'G'RI" if ok else "XATOLAR BOR")
    return ok


def main(argv=None):
    p = argparse.ArgumentParser(description="SAFF Vazifalar 2.0 — sinov ma'lumoti")
    p.add_argument("--reset", action="store_true", help="tozalab, qaytadan to'ldiradi")
    p.add_argument("--wipe", action="store_true", help="faqat tozalaydi")
    p.add_argument("--force", action="store_true", help="bazada ma'lumot bo'lsa ham to'ldiradi")
    p.add_argument("--months", type=int, default=3, help="necha oylik tarix (standart 3)")
    args = p.parse_args(argv)

    # Skript mustaqil ishlashi kerak: API ko'tarilmagan bo'lsa ham jadvallarni o'zi yaratadi.
    from .db import Base, engine
    Base.metadata.create_all(engine)
    if engine.dialect.name == "postgresql":
        from sqlalchemy import text
        with engine.begin() as c:
            c.execute(text("CREATE SEQUENCE IF NOT EXISTS task_code_seq START 1000"))

    db = SessionLocal()
    try:
        seed(db)
        if args.reset or args.wipe:
            wipe(db)
            print("Baza tozalandi.")
            if args.wipe:
                return 0
        existing = db.execute(select(func.count()).select_from(Task)).scalar() or 0
        if existing and not args.force:
            print(f"Bazada {existing} ta vazifa bor. --reset yoki --force ishlating.")
            return 1
        people = make_people(db)
        db.commit()
        n = make_tasks(db, people, months=args.months)
        svc.sync_code_sequence(db)
        db.commit()
        print(f"{n} ta vazifa yaratildi.")
        return 0 if report(db) else 2
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
