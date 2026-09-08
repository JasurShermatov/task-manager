"""FAKER — sinov uchun soxta ma'lumot generatori. Prodda ishlatilmaydi.

Bitta buyruq bilan bazaga (Postgres yoki SQLite) to'liq, real qurilishga o'xshash
ma'lumot yozadi: loyihalar, blok/qavat/zona daraxti, xodimlar, shablonlar, vazifalar,
checklist, bog'liqliklar, kunlik hisobotlar, fotolar, izohlar, tarix, bildirishnomalar
va takroriy vazifa qoidalari — ya'ni barcha jadvallar.

    docker compose -f docker-compose.prod.yml exec api python -m app.fake_data          # to'ldiradi
    docker compose -f docker-compose.prod.yml exec api python -m app.fake_data --reset  # tozalab qaytadan
    docker compose -f docker-compose.prod.yml exec api python -m app.fake_data --wipe   # FAQAT tozalaydi

--wipe soxta ma'lumotni bazadan olib tashlaydi: admin foydalanuvchi, rollar va ish
turlari joyida qoladi, ya'ni tizim toza holatda ishlayveradi.

Mantiq qurilishdagidek: har blokda pastki qavatlar bitgan, o'rtasi jarayonda,
yuqorisi rejada. Ish turlari zanjir bo'lib boradi (armatura -> beton -> devor -> ...),
ba'zilari material yo'qligi yoki ob-havo sababli bloklangan.
"""
from __future__ import annotations

import argparse
import random
import struct
import sys
import zlib
from datetime import date, datetime, timedelta

from sqlalchemy import delete, select

from .auth import hash_password
from .config import settings
from .db import SessionLocal, engine, Base
from .models import (Project, Location, Role, User, TaskType, TaskTemplate, Task, TaskChecklistItem,
                     TaskDependency, TaskDailyProgress, TaskAttachment, TaskComment, TaskHistory,
                     Notification, TaskRecurringRule, Job, TelegramLinkCode, RefreshToken)
from .services import files as fsvc
from .services import tasks as svc
from .seed import seed

R = random.Random(20260907)

PROJECTS = [
    ("YUN-01", "Yunusobod 12 turar-joy majmuasi", ["A blok", "B blok", "C blok"], 16),
    ("SGL-02", "Sergeli Yangi Shahar 4-mavze", ["1-uy", "2-uy"], 12),
    ("CHL-03", "Chilonzor Business Center", ["Ofis minorasi"], 14),
    ("MRZ-04", "Mirzo Ulug'bek Residence", ["A blok", "B blok"], 9),
    ("SAM-05", "Samarqand Registon Plaza", ["Savdo markazi", "Mehmonxona"], 7),
    ("BUX-06", "Buxoro Silk Road Hotel", ["Asosiy korpus"], 5),
    ("NAM-07", "Namangan Sanoat Ombori", ["Ombor 1", "Ombor 2"], 2),
    ("FRG-08", "Farg'ona Tibbiyot Markazi", ["Poliklinika", "Statsionar"], 6),
    ("AND-09", "Andijon Maktab 42", ["O'quv korpusi", "Sport zali"], 4),
    ("QAR-10", "Qarshi Logistika Terminali", ["Terminal A"], 3),
    ("TER-11", "Termiz Chegara Bozori", ["Bozor korpusi"], 3),
    ("NUK-12", "Nukus Turar-joy 7-kvartal", ["A blok", "B blok"], 10),
]

# ism -> rol. Qurilish kompaniyasining tipik shtati.
STAFF = {
    "rahbar": [("Anvar Rustamov", "arustamov"), ("Shuhrat Yo'ldoshev", "syuldoshev"),
               ("Bekzod Nazarov", "bnazarov")],
    "prorab": [("Sardor Karimov", "skarimov"), ("Jasur Ergashev", "jergashev"),
               ("Otabek Tursunov", "otursunov"), ("Dilshod Qodirov", "dqodirov"),
               ("Ravshan Xolmatov", "rxolmatov"), ("Ulug'bek Sattorov", "usattorov"),
               ("Farrux Abdullayev", "fabdullayev")],
    "bajaruvchi": [("Rustam Ergashev", "rergashev"), ("Aziz Toshmatov", "atoshmatov"),
                   ("Murod Yusupov", "myusupov"), ("Sanjar Aliyev", "saliyev"),
                   ("Bobur Mahmudov", "bmahmudov"), ("Doston Rahimov", "drahimov"),
                   ("Nodir Ismoilov", "nismoilov"), ("Islom Xasanov", "ixasanov"),
                   ("Temur G'aniyev", "tganiyev"), ("Javohir Umarov", "jumarov"),
                   ("Akmal Sobirov", "asobirov"), ("Kamol Jo'rayev", "kjurayev"),
                   ("Sherzod Nematov", "snematov"), ("Alisher Qosimov", "aqosimov"),
                   ("Elyor Hakimov", "ehakimov"), ("Sardorbek Aminov", "saminov")],
    "tekshiruvchi": [("Doniyor Toshmatov", "dtoshmatov"), ("Zafar Mirzayev", "zmirzayev"),
                     ("Oybek Salimov", "osalimov")],
    "kuzatuvchi": [("Malika Ahmedova", "mahmedova"), ("Nigora Yusupova", "nyusupova")],
}
FAKE_PASSWORD = "1234"

# qurilish ketma-ketligi: (ish turi nomi, kunlar, hajm, birlik)
SEQUENCE = [
    ("Armatura ishlari", 4, (2.0, 6.0), "t"),
    ("Beton ishlari", 5, (120, 260), "m3"),
    ("Devor terimi", 7, (180, 420), "m2"),
    ("Gidroizolyatsiya", 3, (60, 140), "m2"),
    ("Elektr montaj", 4, (300, 900), "m"),
    ("Santexnika", 4, (120, 380), "m"),
    ("Suvoq ishlari", 6, (250, 600), "m2"),
    ("Pol qoplamasi", 5, (180, 420), "m2"),
    ("Fasad ishlari", 8, (200, 500), "m2"),
]

BLOCK_REASONS = ["material_yoq", "hujjat_kutilmoqda", "texnika_band", "ishchi_yetmadi", "obhavo", "qaror_kutilmoqda"]
BLOCK_NOTES = {
    "material_yoq": ["Sement yetkazilmadi, ta'minotchi 2 kun kechikdi", "Armatura A500 tugadi",
                     "G'isht partiyasi kelmadi", "Gidroizolyatsiya materiali yo'q"],
    "hujjat_kutilmoqda": ["Loyihachidan o'zgartirilgan chizma kutilmoqda", "KJ bo'limi chizmasi tasdiqlanmagan"],
    "texnika_band": ["Kran boshqa blokda ishlayapti", "Beton nasos band", "Vishka yo'q"],
    "ishchi_yetmadi": ["Brigada boshqa obyektga o'tkazildi", "5 ta ishchi kasal"],
    "obhavo": ["Kuchli yomg'ir, beton quyish to'xtatildi", "Harorat -8, beton ishlari to'xtadi"],
    "qaror_kutilmoqda": ["Buyurtmachi pol qoplamasi turini tanlamadi", "Rahbariyat qarori kutilmoqda"],
}
RETURN_REASONS = ["Yuza tekis emas, qayta ishlash kerak", "Foto sifatsiz, qayta suratga oling",
                  "Himoya qatlami yetarli emas", "Choklar to'ldirilmagan"]
COMMENTS = ["Bugun brigada 8 kishi bilan ishladi", "Material yetkazildi, ertaga davom etamiz",
            "Buyurtmachi ko'rikdan o'tkazdi", "Kran ertaga bo'shaydi", "Rahmat, tez bajarildi",
            "Chizmaga mos bajarildi", "Ertaga tekshiruvga tayyor bo'ladi"]
DAILY_NOTES = ["Reja bo'yicha ketyapti", "Yomg'ir tufayli sekinlashdi", "Qo'shimcha brigada qo'shildi",
               "Texnika to'xtab qoldi, 2 soat yo'qotildi", ""]


def png(w=320, h=240, rgb=(120, 130, 140)) -> bytes:
    """Kichik haqiqiy PNG (kutubxonasiz) — soxta fotolar uchun."""
    raw = b"".join(b"\x00" + bytes(rgb) * w for _ in range(h))

    def chunk(tag, data):
        c = tag + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 6))
            + chunk(b"IEND", b""))


def wipe(db):
    """Soxta ma'lumotni tozalaydi (admin, rollar va ish turlari qoladi)."""
    for model in (TaskHistory, TaskComment, TaskAttachment, TaskDailyProgress, TaskChecklistItem,
                  TaskDependency, Notification, Job, TaskRecurringRule, Task, TaskTemplate,
                  TelegramLinkCode, RefreshToken):
        db.execute(delete(model))
    db.execute(delete(Location))
    db.execute(delete(Project))
    db.execute(delete(User).where(User.login != settings.ADMIN_LOGIN))
    db.commit()


def build(db, reset=False):
    Base.metadata.create_all(engine)
    seed(db)
    if reset:
        wipe(db)
        seed(db)

    roles = {r.code: r for r in db.scalars(select(Role))}
    admin = db.scalar(select(User).where(User.login == settings.ADMIN_LOGIN))
    types = {t.name: t for t in db.scalars(select(TaskType))}

    # ---------- loyihalar va joylar ----------
    projects = []
    for code, name, blocks, floors in PROJECTS:
        p = db.scalar(select(Project).where(Project.code == code))
        if not p:
            p = Project(code=code, name=name)
            db.add(p)
            db.flush()
        existing = db.scalars(select(Location).where(Location.project_id == p.id)).all()
        if not existing:
            for bi, bname in enumerate(blocks):
                b = Location(project_id=p.id, name=bname, kind="block", sort_order=bi)
                db.add(b)
                db.flush()
                for fi in range(1, floors + 1):
                    f = Location(project_id=p.id, parent_id=b.id, name=f"{fi}-qavat", kind="floor", sort_order=fi)
                    db.add(f)
                    db.flush()
                    if floors >= 8 and fi % 4 == 0:
                        for z in (1, 2):
                            db.add(Location(project_id=p.id, parent_id=f.id, name=f"Zona {z}", kind="zone", sort_order=z))
        projects.append(p)
    db.flush()
    # seed'dagi bo'sh namuna loyiha soxta ma'lumot bilan aralashmasin
    stub = db.scalar(select(Project).where(Project.code == "SAFF-01"))
    if stub and not db.scalar(select(Task).where(Task.project_id == stub.id).limit(1)):
        db.execute(delete(TaskTemplate).where(TaskTemplate.id.in_(
            select(TaskTemplate.id).where(TaskTemplate.name == "Monolit plita — qavat"))))
        db.execute(delete(Location).where(Location.project_id == stub.id))
        db.delete(stub)
        db.flush()
        projects = [x for x in projects if x.id != stub.id]
    # bitta obyekt arxivda bo'lsin (real hayotda tugagan obyekt)
    projects[-1].is_active = False
    db.flush()
    active_projects = [p for p in projects if p.is_active]

    # ---------- xodimlar ----------
    def mkuser(name, login, role, scope_type="system", scope_id=None, lang="uz"):
        u = db.scalar(select(User).where(User.login == login))
        if u:
            return u
        u = User(full_name=name, login=login, password_hash=hash_password(FAKE_PASSWORD),
                 role_id=roles[role].id, scope_type=scope_type, scope_id=scope_id, lang=lang,
                 phone=f"+9989{R.randint(10, 99)}{R.randint(1000000, 9999999)}")
        db.add(u)
        db.flush()
        return u

    rahbars, prorabs, workers, qcs, watchers = [], [], [], [], []
    for i, (name, login) in enumerate(STAFF["rahbar"]):
        rahbars.append(mkuser(name, login, "rahbar", "project", active_projects[i % len(active_projects)].id))
    # prorablar faqat faol loyihalarning bloklariga biriktiriladi
    active_ids = [p.id for p in active_projects]
    blocks_all = db.scalars(select(Location).where(Location.kind == "block", Location.project_id.in_(active_ids))
                            .order_by(Location.project_id, Location.sort_order)).all()
    for i, (name, login) in enumerate(STAFF["prorab"]):
        prorabs.append(mkuser(name, login, "prorab", "location", blocks_all[i % len(blocks_all)].id))
    for i, (name, login) in enumerate(STAFF["bajaruvchi"]):
        workers.append(mkuser(name, login, "bajaruvchi", "system", None, "uz" if i % 4 else "ru"))
    for i, (name, login) in enumerate(STAFF["tekshiruvchi"]):
        qcs.append(mkuser(name, login, "tekshiruvchi", "project", active_projects[i % len(active_projects)].id))
    for i, (name, login) in enumerate(STAFF["kuzatuvchi"]):
        watchers.append(mkuser(name, login, "kuzatuvchi", "project", active_projects[i].id))
    # bitta bloklangan xodim (real holat)
    workers[-1].is_active = False
    db.flush()
    active_workers = [w for w in workers if w.is_active]

    # ---------- shablonlar ----------
    if db.scalar(select(Task).limit(1)) is None:
        for tname, days, _, _ in SEQUENCE[:5]:
            tt = types.get(tname)
            if tt and not db.scalar(select(TaskTemplate).where(TaskTemplate.name == f"{tname} — qavat")):
                db.add(TaskTemplate(name=f"{tname} — qavat", type_id=tt.id,
                                    title_pattern=f"{tname} — {{joy}}", default_duration_days=days,
                                    checklist_json=tt.default_checklist_json,
                                    required_evidence_kinds=tt.required_evidence_kinds))
    db.flush()

    today = date.today()
    seq_no = 1000
    created_tasks: list[Task] = []
    photo_bytes = {k: png(rgb=c) for k, c in
                   (("before", (150, 150, 155)), ("during", (110, 125, 145)), ("after", (120, 145, 120)))}

    def add_history(task, action, actor, when, old=None, new=None, source="web"):
        db.add(TaskHistory(task_id=task.id, action=action, old_values_json=old or {}, new_values_json=new or {},
                           actor_id=actor.id if actor else None, source=source, request_id=f"fake{R.randint(1000,9999)}",
                           created_at=when))

    def add_photo(task, kind, uploader, when):
        data = photo_bytes[kind]
        key = fsvc.store(data, f"{task.code}_{kind}.png")
        db.add(TaskAttachment(task_id=task.id, kind=kind, storage_key=key, filename=f"{task.code}_{kind}.png",
                              mime_type="image/png", size=len(data), captured_at=when, source=R.choice(("web", "bot")),
                              uploaded_by=uploader.id, created_at=when))

    for p in active_projects:
        blocks = db.scalars(select(Location).where(Location.project_id == p.id, Location.kind == "block")
                            .order_by(Location.sort_order)).all()
        rahbar = next((r for r in rahbars if r.scope_id == p.id), rahbars[0])
        qc = next((q for q in qcs if q.scope_id == p.id), qcs[0])
        # har obyektda o'zining barqaror brigadasi bo'ladi - ishchi 9 ta obyektda sochilib yurmaydi
        brigade = R.sample(active_workers, k=min(4, len(active_workers)))
        for b in blocks:
            floors = db.scalars(select(Location).where(Location.parent_id == b.id).order_by(Location.sort_order)).all()
            if not floors:
                continue
            prorab = next((pr for pr in prorabs if pr.scope_id == b.id), R.choice(prorabs))
            # blok qaysi qavatgacha ko'tarilgan
            front = max(1, int(len(floors) * R.uniform(0.35, 0.75)))
            for fi, floor in enumerate(floors, start=1):
                if fi > front + 3:            # juda yuqori qavatlar hali rejada ham emas
                    continue
                works = SEQUENCE if fi <= front else SEQUENCE[:R.randint(2, 4)]
                prev_task = None
                base = today - timedelta(days=(front - fi) * 9) if fi <= front else today + timedelta(days=(fi - front) * 7)
                for wi, (tname, days, qty_range, unit) in enumerate(works):
                    tt = types.get(tname)
                    if not tt:
                        continue
                    start = base + timedelta(days=wi * max(2, days - 2))
                    end = start + timedelta(days=days - 1)
                    seq_no += 1
                    worker = R.choice(brigade)
                    plan_qty = round(R.uniform(*qty_range), 1)
                    task = Task(code=f"V-{seq_no}", project_id=p.id, location_id=floor.id, type_id=tt.id,
                                title=f"{tname} — {b.name} {floor.name}",
                                description=R.choice([None, f"{b.name} {floor.name} bo'yicha chizma KJ-{R.randint(1,9)} ga muvofiq bajarilsin."]),
                                status="plan", priority=R.choices(["low", "normal", "high"], [2, 6, 2])[0],
                                assignee_id=worker.id, reviewer_id=qc.id,
                                planned_start=start, planned_end=end,
                                planned_quantity=plan_qty, unit=unit,
                                planned_crew_size=R.randint(3, 12),
                                created_by=(prorab if R.random() < .6 else rahbar).id,
                                created_at=datetime.combine(start - timedelta(days=R.randint(1, 5)), datetime.min.time()))
                    db.add(task)
                    db.flush()
                    created_tasks.append(task)
                    add_history(task, "create", prorab, task.created_at,
                                new={"title": task.title, "assignee_id": worker.id, "planned_end": str(end)})

                    for i, c in enumerate(tt.default_checklist_json or []):
                        db.add(TaskChecklistItem(task_id=task.id, title=c["title"],
                                                 is_required=c.get("is_required", True), sort_order=i))
                    if prev_task is not None:
                        db.add(TaskDependency(task_id=task.id, depends_on_task_id=prev_task.id))
                    prev_task = task
                    db.flush()

                    # ---- holat: qavat qanchalik pastda bo'lsa, shuncha tugagan ----
                    if end < today - timedelta(days=3):
                        state = R.choices(["done", "review", "blocked", "progress"], [80, 6, 7, 7])[0]
                    elif start <= today <= end + timedelta(days=3):
                        state = R.choices(["progress", "review", "blocked", "plan"], [55, 15, 12, 18])[0]
                    else:
                        state = "plan"
                    apply_state(db, task, state, worker, qc, prorab, rahbar, today, add_history, add_photo)

    # ---------- bir nechta o'qilmagan bildirishnoma (qo'ng'iroq bo'sh turmasin) ----------
    recent = [t for t in created_tasks if t.status in ("review", "blocked")][:12]
    for t in recent:
        for uid in {admin.id, t.reviewer_id}:
            db.add(Notification(user_id=uid, task_id=t.id,
                                event="submitted_review" if t.status == "review" else "blocked",
                                payload_json={"code": t.code, "title": t.title,
                                              "reason": t.blocked_reason, "note": t.blocked_note},
                                channel="inapp", status="sent", is_read=False, sent_at=datetime.utcnow()))
    db.commit()
    return created_tasks


def apply_state(db, task, state, worker, qc, prorab, rahbar, today, add_history, add_photo):
    """Vazifani berilgan holatga real yo'l bilan olib boradi: tarix, checklist, hisobot, foto."""
    started = datetime.combine(task.planned_start, datetime.min.time()) + timedelta(hours=8)
    items = db.scalars(select(TaskChecklistItem).where(TaskChecklistItem.task_id == task.id)).all()

    def tick(all_required=True):
        for it in items:
            if all_required or R.random() < .5:
                it.is_done = True
                it.done_by = worker.id
                it.done_at = started + timedelta(days=R.randint(0, 3))

    def daily_rows(n, total_share):
        got = 0.0
        for i in range(n):
            d = task.planned_start + timedelta(days=i)
            if d > today:
                break
            q = round(float(task.planned_quantity) * total_share / max(1, n), 1)
            got += q
            db.add(TaskDailyProgress(task_id=task.id, date=d, quantity=q,
                                     workers_count=R.randint(3, 14), work_hours=R.choice([8, 8, 9, 10]),
                                     note=R.choice(DAILY_NOTES) or None, source=R.choice(("web", "bot", "bot")),
                                     created_by=worker.id,
                                     created_at=datetime.combine(d, datetime.min.time()) + timedelta(hours=18)))
        return got

    if state == "plan":
        task.progress_percent = 0
        return

    task.status = "progress"
    task.actual_start = started
    add_history(task, "start", worker, started, {"status": "plan"}, {"status": "progress"}, R.choice(("web", "bot")))

    if state == "progress":
        tick(all_required=False)
        got = daily_rows(R.randint(1, 4), R.uniform(.2, .7))
        task.actual_quantity = round(got, 1)
        done = sum(1 for i in items if i.is_done)
        task.progress_percent = int(done / len(items) * 100) if items else int(got / float(task.planned_quantity) * 100)
        if R.random() < .35:
            add_photo(task, "during", worker, started + timedelta(days=1))
        if R.random() < .25:
            task.return_count = 1
            add_history(task, "return", qc, started + timedelta(days=2), {"status": "review"},
                        {"status": "progress", "reason": R.choice(RETURN_REASONS)})
        return

    if state == "blocked":
        tick(all_required=False)
        got = daily_rows(R.randint(1, 3), R.uniform(.15, .5))
        task.actual_quantity = round(got, 1)
        task.previous_status = "progress"
        task.status = "blocked"
        task.blocked_reason = R.choice(BLOCK_REASONS)
        task.blocked_note = R.choice(BLOCK_NOTES[task.blocked_reason])
        task.blocked_at = datetime.utcnow() - timedelta(days=R.randint(1, 9), hours=R.randint(0, 20))
        done = sum(1 for i in items if i.is_done)
        task.progress_percent = int(done / len(items) * 100) if items else 0
        add_history(task, "block", worker, task.blocked_at, {"status": "progress"},
                    {"status": "blocked", "reason": task.blocked_reason, "note": task.blocked_note},
                    R.choice(("web", "bot")))
        return

    # review yoki done — majburiy checklist va fotolar to'liq
    tick(all_required=True)
    got = daily_rows(R.randint(2, 5), R.uniform(.85, 1.08))
    task.actual_quantity = round(got, 1)
    task.quantity_over_plan = got > float(task.planned_quantity)
    from .models import TaskType
    tt = db.get(TaskType, task.type_id)
    for kind in (tt.required_evidence_kinds or ["after"]):
        add_photo(task, kind, worker, started + timedelta(days=1))
    dur = max(1, (task.planned_end - task.planned_start).days)
    if R.random() < .75:                      # muddatida topshirilgan
        submitted = started + timedelta(days=max(1, dur - R.randint(1, 3)))
    else:                                     # kechikkan
        submitted = started + timedelta(days=dur + R.randint(2, 7))
    task.status = "review"
    task.review_started_at = submitted
    task.progress_percent = 100 if not items else int(sum(1 for i in items if i.is_done) / len(items) * 100)
    add_history(task, "submit_review", worker, submitted, {"status": "progress"}, {"status": "review"},
                R.choice(("web", "bot")))
    if R.random() < .2:
        task.return_count = 1

    if state == "review":
        # navbatda turibdi — ba'zilari uzoq turib qolgan (tiqilish ko'rinsin)
        task.review_started_at = datetime.utcnow() - timedelta(days=R.randint(0, 7), hours=R.randint(0, 20))
        return

    accepted = submitted + timedelta(days=R.randint(0, 1))
    task.status = "done"
    task.actual_end = accepted
    task.progress_percent = 100
    add_history(task, "accept", qc, accepted, {"status": "review"}, {"status": "done"})
    if R.random() < .3:
        db.add(TaskComment(task_id=task.id, text=R.choice(COMMENTS), author_id=R.choice([qc.id, prorab.id]),
                           mentions_json=[], source=R.choice(("web", "bot")), created_at=accepted))


def add_recurring_rules(db, tasks):
    """Takroriy vazifa qoidalari (masalan haftalik xavfsizlik ko'rigi)."""
    if db.scalar(select(TaskRecurringRule).limit(1)):
        return 0
    tmpl = db.scalars(select(TaskTemplate)).all()
    if not tmpl or not tasks:
        return 0
    n = 0
    for t in tasks[:6]:
        db.add(TaskRecurringRule(
            template_id=R.choice(tmpl).id, project_id=t.project_id, location_id=t.location_id,
            assignee_id=t.assignee_id, reviewer_id=t.reviewer_id,
            rrule=R.choice(["FREQ=DAILY", "FREQ=WEEKLY;BYDAY=MO,WE,FR", "FREQ=WEEKLY;BYDAY=SA"]),
            next_run_at=date.today() + timedelta(days=R.randint(1, 7)), is_active=True))
        n += 1
    return n


def report(db):
    """Nima yozilgani va mantiq to'g'riligi — bir qarashda ko'rinsin."""
    from .models import Task as T
    rows = [(Project, "loyiha"), (Location, "joy"), (User, "xodim"), (TaskType, "ish turi"),
            (TaskTemplate, "shablon"), (Task, "vazifa"), (TaskChecklistItem, "checklist bandi"),
            (TaskDependency, "bog'liqlik"), (TaskDailyProgress, "kunlik hisobot"),
            (TaskAttachment, "foto/hujjat"), (TaskComment, "izoh"), (TaskHistory, "tarix yozuvi"),
            (Notification, "bildirishnoma"), (TaskRecurringRule, "takroriy qoida")]
    print("\n  Jadval bo'yicha:")
    for model, label in rows:
        print(f"    {db.query(model).count():>6}  {label}")
    counts = {}
    for t in db.scalars(select(T)):
        counts[t.status] = counts.get(t.status, 0) + 1
    print("\n  Holatlar: " + " · ".join(f"{k}={v}" for k, v in sorted(counts.items())))

    # mantiq tekshiruvi - soxta ma'lumot ham qoidalarga bo'ysunishi kerak
    bad = []
    for t in db.scalars(select(T)):
        if t.status == "done" and (t.progress_percent != 100 or not t.actual_end):
            bad.append(f"{t.code}: bajarilgan, lekin progress/sana to'liq emas")
        if t.status == "blocked" and not (t.blocked_reason and t.previous_status):
            bad.append(f"{t.code}: bloklangan, lekin sabab yo'q")
        if t.status == "plan" and t.progress_percent:
            bad.append(f"{t.code}: rejada, lekin progress bor")
        if t.assignee_id == t.reviewer_id:
            bad.append(f"{t.code}: bajaruvchi va tekshiruvchi bir odam")
    codes = [t.code for t in db.scalars(select(T))]
    if len(codes) != len(set(codes)):
        bad.append("takrorlangan vazifa kodi bor")
    print("\n  Mantiq tekshiruvi: " + ("HAMMASI TO'G'RI" if not bad else f"{len(bad)} ta muammo"))
    for b in bad[:5]:
        print("    ! " + b)
    return not bad


def main():
    ap = argparse.ArgumentParser(description="Soxta (sinov) ma'lumot generatori")
    ap.add_argument("--force", action="store_true", help="vazifalar bor bo'lsa ham qo'shish")
    ap.add_argument("--reset", action="store_true", help="tozalab qaytadan yaratish")
    ap.add_argument("--wipe", action="store_true", help="FAQAT tozalash - hech narsa yaratmaydi")
    a = ap.parse_args()
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        if a.wipe:
            wipe(db)
            seed(db)
            svc.sync_code_sequence(db)
            db.commit()
            print("Soxta ma'lumot tozalandi. Admin, rollar va ish turlari joyida.")
            report(db)
            return 0
        if db.scalar(select(Task).limit(1)) and not (a.force or a.reset):
            print("Bazada vazifalar bor. --reset (tozalab qaytadan) yoki --force (ustiga qo'shish) bering.")
            return 1
        tasks = build(db, reset=a.reset)
        add_recurring_rules(db, tasks)
        # Postgres kod ketma-ketligi: bu yerda satrlar to'g'ridan-to'g'ri yozilgani uchun
        # ketma-ketlik orqada qoladi -> keyin yangi vazifa yaratishda kod to'qnashadi.
        top = svc.sync_code_sequence(db)
        db.commit()
        print(f"\nTayyor: {len(tasks)} ta vazifa yaratildi.")
        if top:
            print(f"  Kod ketma-ketligi tekislandi: keyingi vazifa V-{top + 1} dan boshlanadi.")
        ok = report(db)
        print(f"\n  Xodimlar paroli: {FAKE_PASSWORD}")
        print("  Kirish uchun: arustamov (rahbar) · skarimov (prorab) · rergashev (ishchi) · "
              "dtoshmatov (tekshiruvchi) · mahmedova (kuzatuvchi)")
        return 0 if ok else 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
