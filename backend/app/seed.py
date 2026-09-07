"""Idempotent seed: system roles, admin user, default task types, demo project (only if DB empty)."""
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import hash_password
from .config import settings
from .models import Role, User, TaskType, Project, Location, TaskTemplate
from .permissions import SYSTEM_ROLES

DEFAULT_TYPES = [
    ("Beton ishlari", "Monolit", 5, ["before", "during", "after"],
     [{"title": "Qolip o'rnatildi va tekshirildi", "is_required": True}, {"title": "Armatura qabul qilindi", "is_required": True},
      {"title": "Beton quyildi", "is_required": True}, {"title": "Beton parvarishi boshlandi", "is_required": False}]),
    ("Armatura ishlari", "Monolit", 4, ["during", "after"],
     [{"title": "Armatura chizma bo'yicha bog'landi", "is_required": True}, {"title": "Himoya qatlami tekshirildi", "is_required": True}]),
    ("Devor terimi", "Umumiy qurilish", 6, ["before", "after"],
     [{"title": "O'qlar belgilandi", "is_required": True}, {"title": "Terim gorizontal/vertikal tekshirildi", "is_required": True},
      {"title": "Choklar to'ldirildi", "is_required": False}]),
    ("Suvoq ishlari", "Pardozlash", 5, ["before", "after"],
     [{"title": "Yuza tayyorlandi", "is_required": True}, {"title": "Suvoq tekisligi tekshirildi", "is_required": True}]),
    ("Pol qoplamasi", "Pardozlash", 4, ["before", "after"],
     [{"title": "Asos tekisligi tekshirildi", "is_required": True}, {"title": "Qoplama yotqizildi", "is_required": True}]),
    ("Elektr montaj", "Muhandislik", 3, ["during", "after"],
     [{"title": "Shtroba tayyor", "is_required": True}, {"title": "Kabel yotqizildi", "is_required": True}, {"title": "Izolyatsiya tekshirildi", "is_required": True}]),
    ("Santexnika", "Muhandislik", 3, ["during", "after"],
     [{"title": "Quvurlar o'rnatildi", "is_required": True}, {"title": "Bosim sinovi o'tkazildi", "is_required": True}]),
    ("Gidroizolyatsiya", "Umumiy qurilish", 3, ["before", "during", "after"],
     [{"title": "Yuza quruq va toza", "is_required": True}, {"title": "2 qatlam yotqizildi", "is_required": True}]),
    ("Fasad ishlari", "Fasad", 7, ["before", "after"],
     [{"title": "Karkas o'rnatildi", "is_required": True}, {"title": "Panellar mahkamlandi", "is_required": True}]),
    ("Umumiy vazifa", "Umumiy", 3, ["after"],
     [{"title": "Ish bajarildi", "is_required": True}]),
]


def seed(db: Session):
    roles = {r.code: r for r in db.scalars(select(Role))}
    for code, name, perms in SYSTEM_ROLES:
        if code not in roles:
            r = Role(code=code, name=name, permissions_json=perms, is_system=True)
            db.add(r)
            roles[code] = r
        else:
            roles[code].permissions_json = perms if roles[code].is_system and code == "admin" else roles[code].permissions_json
    db.flush()

    if not db.scalar(select(User).limit(1)):
        db.add(User(full_name="Administrator", login=settings.ADMIN_LOGIN, password_hash=hash_password(settings.ADMIN_PASSWORD),
                    role_id=roles["admin"].id, scope_type="system", lang="uz"))

    if not db.scalar(select(TaskType).limit(1)):
        for name, grp, days, kinds, ck in DEFAULT_TYPES:
            db.add(TaskType(name=name, group_name=grp, default_duration_days=days, required_evidence_kinds=kinds,
                            default_checklist_json=[{**c, "sort_order": i} for i, c in enumerate(ck)]))
    db.flush()

    if not db.scalar(select(Project).limit(1)):
        p = Project(code="SAFF-01", name="Birinchi obyekt")
        db.add(p)
        db.flush()
        a = Location(project_id=p.id, name="A blok", kind="block", sort_order=0)
        db.add(a)
        db.flush()
        for i in range(1, 4):
            f = Location(project_id=p.id, parent_id=a.id, name=f"{i}-qavat", kind="floor", sort_order=i)
            db.add(f)
        db.flush()
        beton = db.scalar(select(TaskType).where(TaskType.name == "Beton ishlari"))
        if beton:
            db.add(TaskTemplate(name="Monolit plita — qavat", type_id=beton.id, title_pattern="Monolit plita — {joy} betonlash",
                                default_duration_days=5, checklist_json=beton.default_checklist_json,
                                required_evidence_kinds=beton.required_evidence_kinds))
    db.commit()
