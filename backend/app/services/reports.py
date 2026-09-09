"""Hisobot: kim nechta oldi, nechtasini vaqtida bajardi, necha kun kechikdi.

Bir odamning davr ichidagi vazifalari to'rt guruhga bo'linadi va ular yig'indisi "berilgan"ga
teng bo'ladi — hisobot o'zini o'zi tekshiradi:

    berilgan = vaqtida + kechikib bajarilgan + bajarilmagan + jarayonda

Bekor qilinganlar umuman hisobga olinmaydi (odamning aybi emas).
Foiz = vaqtida / berilgan.
"""
from __future__ import annotations

import csv
import io
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import clock
from ..models import CANCELLED, DONE, NEW, PROGRESS, SUBMITTED, Department, Task, User
from . import xlsx

FIELDS = ["given", "on_time", "late_done", "not_done", "in_progress", "returned"]


def _blank(u: User | None = None, dep: Department | None = None) -> dict:
    return {
        "user_id": u.id if u else 0,
        "full_name": u.full_name if u else "Jami",
        "role": u.role if u else "",
        "position": u.position if u else None,
        "department_id": dep.id if dep else None,
        "department_name": dep.name if dep else None,
        **{f: 0 for f in FIELDS},
        "_late_seconds": 0, "_late_count": 0,
        "avg_late_days": 0.0, "percent": 0.0,
    }


def _finish(row: dict) -> dict:
    row["avg_late_days"] = round(row.pop("_late_seconds") / 86400 / row["_late_count"], 1) \
        if row["_late_count"] else 0.0
    row.pop("_late_count", None)
    # Foiz = vaqtida bajarilgan / berilgan. Oddiy va oldindan aytib bo'ladigan:
    # vazifa soni o'zgarsa foiz ham o'zgaradi.
    row["percent"] = round(row["on_time"] / row["given"] * 100, 1) if row["given"] else 0.0
    return row


def summary(db: Session, date_from: date, date_to: date, *, role: str | None = None,
            department_id: int | None = None, ref: datetime | None = None) -> dict:
    ref = ref or clock.now()
    start, end = clock.at(date_from, 0, 0), clock.at(date_to, 23, 59)

    users = {u.id: u for u in db.scalars(select(User).order_by(User.full_name))}
    deps = {d.id: d for d in db.scalars(select(Department))}

    wanted = [u for u in users.values()
              if (not role or u.role in role.split(","))
              and (not department_id or u.department_id == department_id)]
    rows = {u.id: _blank(u, deps.get(u.department_id)) for u in wanted}
    totals = _blank()

    tasks = db.scalars(select(Task).where(Task.created_at >= start, Task.created_at <= end,
                                          Task.status != CANCELLED)).all()
    for t in tasks:
        row = rows.get(t.assignee_id)
        if row is None:
            continue
        late = t.late_seconds(ref)
        for target in (row, totals):
            target["given"] += 1
            target["returned"] += t.return_count
        if t.status == DONE:
            bucket = "late_done" if late > 0 else "on_time"
        elif t.status in (NEW, PROGRESS) and t.due_at < ref:
            bucket = "not_done"
        else:
            bucket = "in_progress"          # jarayonda yoki topshirilgan, qabul kutilmoqda
        for target in (row, totals):
            target[bucket] += 1
            if late > 0:
                target["_late_seconds"] += late
                target["_late_count"] += 1

    out = [_finish(r) for r in rows.values()]
    out.sort(key=lambda r: (-r["given"], r["full_name"]))
    return {"date_from": date_from, "date_to": date_to,
            "rows": out, "totals": _finish(totals)}


# ---------------------------------------------------------------- eksport
HEADERS = ["Kim", "Rol", "Lavozim", "Bo'lim", "Berilgan", "Vaqtida", "Kechikib bajarildi",
           "Bajarilmadi", "Jarayonda", "Qaytarilgan", "O'rtacha kechikish (kun)", "Foiz %"]


def _values(r: dict, role_label) -> list:
    return [r["full_name"], role_label(r["role"]), r.get("position") or "",
            r.get("department_name") or "", r["given"], r["on_time"], r["late_done"],
            r["not_done"], r["in_progress"], r["returned"], r["avg_late_days"], r["percent"]]


def to_csv(report: dict, role_label) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow([f"SAFF Vazifalar — hisobot {report['date_from']} … {report['date_to']}"])
    w.writerow([])
    w.writerow(HEADERS)
    for r in report["rows"]:
        w.writerow(_values(r, role_label))
    w.writerow([])
    w.writerow(_values({**report["totals"], "full_name": "JAMI", "role": ""}, role_label))
    # Excel CSV'ni o'zbekcha harflar bilan to'g'ri ochsin
    return b"\xef\xbb\xbf" + buf.getvalue().encode("utf-8")


WIDTHS = [26, 18, 18, 16, 11, 10, 20, 14, 12, 14, 22, 9]


def to_xlsx(report: dict, role_label) -> bytes:
    rows = [[f"SAFF Vazifalar — hisobot {report['date_from']} … {report['date_to']}"], [], HEADERS]
    rows += [_values(r, role_label) for r in report["rows"]]
    rows += [[], _values({**report["totals"], "full_name": "JAMI", "role": ""}, role_label)]
    styles = {1: xlsx.BOLD, 3: xlsx.HEADER, len(rows): xlsx.BOLD}
    return xlsx.write(rows, sheet_name="Hisobot", styles=styles, widths=WIDTHS, freeze_rows=3)


def bot_table(report: dict, limit: int = 20) -> str:
    """Telegram uchun tekis jadval — moslashuvchan kenglikda, monoshrift ichida chiqadi."""
    rows = report["rows"][:limit]
    if not rows:
        return "—"
    width = min(16, max(len(r["full_name"]) for r in rows))
    lines = []
    for r in rows:
        name = r["full_name"][:width].ljust(width)
        lines.append(f"{name} {r['given']:>3} {r['on_time']:>3}✅ {r['late_done']:>2}⏰ "
                     f"{r['not_done']:>2}✖️ {r['percent']:>5.0f}%")
    t = report["totals"]
    lines.append("─" * (width + 22))
    lines.append(f"{'JAMI'.ljust(width)} {t['given']:>3} {t['on_time']:>3}✅ {t['late_done']:>2}⏰ "
                 f"{t['not_done']:>2}✖️ {t['percent']:>5.0f}%")
    return "\n".join(lines)
