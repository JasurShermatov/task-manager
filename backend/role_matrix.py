"""Rollar kesimidagi haqiqiy matritsani KODDAN chiqarib beradi (qo'lda yozilgan jadval emas).

- bot menyusi   -> bot/render.py dagi MENU + main_menu() ning o'zidan
- web menyusi   -> frontend/src/components/Layout.tsx dan o'qib olinadi
- route himoyasi-> frontend/src/App.tsx dan o'qib olinadi va menyu bilan solishtiriladi
- vazifa tugmalari -> backend/app/services/tasks.py:task_permissions() mantiqidan

Ishga tushirish:  python role_matrix.py            (odam o'qiydigan ko'rinish)
                  python role_matrix.py --json     (artefakt uchun ma'lumot)
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "bot"))
os.environ.setdefault("BOT_TOKEN", "0:matrix")   # bot config faqat import uchun

from app.permissions import SYSTEM_ROLES, ALL_PERMS  # noqa: E402

ROLE_PERMS = {code: set(perms) for code, name, perms in SYSTEM_ROLES}
ROLE_NAMES = {code: name for code, name, perms in SYSTEM_ROLES}
ORDER = ["admin", "rahbar", "prorab", "bajaruvchi", "tekshiruvchi", "kuzatuvchi"]


# ---------------------------------------------------------------- bot
def bot_menu(role: str) -> list[str]:
    import render
    from i18n import t
    keys = [k for k, need, hide in render.MENU
            if (need is None or need in ROLE_PERMS[role]) and role not in hide]
    return [f"{t('uz', k)}" for k in keys]


def bot_menu_keys(role: str) -> list[str]:
    import render
    return [k for k, need, hide in render.MENU
            if (need is None or need in ROLE_PERMS[role]) and role not in hide]


# ---------------------------------------------------------------- web
ITEM_RE = re.compile(r'<Item to="([^"]+)"[^>]*title=\{t\(\'([^\']+)\'\)\}')
CAN_RE = re.compile(r"can\('([^']+)'\)")


def web_nav() -> list[tuple[str, str, list[list[str]]]]:
    """[(route, nav_key, guard)] - guard = OR ro'yxatlari ro'yxati (AND bilan bog'langan)."""
    src = (ROOT / "frontend/src/components/Layout.tsx").read_text()
    nav = src.split("<nav className=\"side__nav\">")[1].split("</nav>")[0]
    out, group_guard = [], None
    for line in nav.splitlines():
        if group_guard is None and line.strip().endswith("&& <>"):
            group_guard = CAN_RE.findall(line)
        m = ITEM_RE.search(line)
        if m:
            route, key = m.groups()
            guards = []
            if group_guard:
                guards.append(group_guard)
            own = CAN_RE.findall(line)
            if own:
                guards.append(own)
            out.append((route, key, guards))
        if "</>}" in line:
            group_guard = None
    return out


def route_guards() -> dict[str, list[str]]:
    """App.tsx: route -> ruxsatlar (OR)."""
    src = (ROOT / "frontend/src/App.tsx").read_text()
    out = {}
    for line in src.splitlines():
        m = re.search(r'<Route path="([^"]+)" element=\{(.*)\}\s*/>', line)
        if not m:
            continue
        route, el = m.groups()
        out[route] = CAN_RE.findall(el) if "<Guard" in el else []
    return out


def sees(role: str, guards: list[list[str]]) -> bool:
    return all(any(p in ROLE_PERMS[role] for p in grp) for grp in guards)


# ---------------------------------------------------------------- task card buttons
def task_buttons(role: str) -> dict[str, str]:
    """services/tasks.py:task_permissions() dagi qoidalar - kim qaysi tugmani ko'radi."""
    p = ROLE_PERMS[role]
    return {
        "Boshlash": "tasks.start" in p,
        "Tekshiruvga yuborish": "tasks.submit_review" in p,
        "Qabul qilish": "tasks.accept" in p,
        "Qaytarish": "tasks.return" in p,
        "Muammo (bloklash)": "tasks.block" in p,
        "Checklist belgilash": "checklist.edit" in p,
        "Kunlik hisobot": "progress.create" in p,
        "Foto biriktirish": "attachments.upload" in p,
        "Izoh": "comments.create" in p,
        "Tahrirlash": "tasks.edit" in p,
        "Mas'ulni almashtirish": "tasks.assign" in p,
        "Muddatni ko'chirish": "tasks.change_dates" in p,
        "Qayta ochish": "tasks.reopen" in p,
        "O'chirish (arxiv)": "tasks.delete" in p,
        "Excel yuklash": "tasks.export" in p,
    }


def can_be(role: str) -> dict[str, bool]:
    p = ROLE_PERMS[role]
    return {"bajaruvchi": "tasks.start" in p, "tekshiruvchi": "tasks.accept" in p}


def scope_of(role: str) -> str:
    return {"admin": "butun tizim", "rahbar": "biriktirilgan loyiha",
            "prorab": "biriktirilgan blok (+ loyihaning umumiy vazifalari)",
            "bajaruvchi": "faqat o'ziga biriktirilgan vazifalar",
            "tekshiruvchi": "biriktirilgan loyiha", "kuzatuvchi": "biriktirilgan loyiha"}[role]


def build() -> dict:
    nav, guards = web_nav(), route_guards()
    problems = []
    # Semantik tekshiruv: har bir rol uchun "menyuda ko'rinadimi" va "manzilga kira oladimi"
    # bir xil javob berishi shart. Aks holda kimdir manzilni qo'lda yozib kirib ketadi.
    for route, key, gs in nav:
        rg = guards.get(route)
        if rg is None:
            problems.append(f"{route}: App.tsx da bunday route yo'q")
            continue
        for role in ORDER:
            in_menu = sees(role, gs)
            can_open = (not rg) or any(p in ROLE_PERMS[role] for p in rg)
            if in_menu != can_open:
                problems.append(f"{route} ({role}): menyu={in_menu}, kirish={can_open}")
    data = {"roles": [], "problems": problems,
            "nav": [{"route": r, "key": k} for r, k, _ in nav]}
    for role in ORDER:
        data["roles"].append({
            "code": role, "name": ROLE_NAMES[role], "scope": scope_of(role),
            "perm_count": len(ROLE_PERMS[role]),
            "bot": bot_menu(role), "bot_keys": bot_menu_keys(role),
            "web": [k for r, k, gs in nav if sees(role, gs)],
            "web_routes": [r for r, k, gs in nav if sees(role, gs)],
            "task_buttons": {k: v for k, v in task_buttons(role).items() if v},
            "can_be": can_be(role),
        })
    return data


if __name__ == "__main__":
    d = build()
    if "--json" in sys.argv:
        print(json.dumps(d, ensure_ascii=False, indent=1))
        sys.exit(0)
    print(f"Ruxsat kodlari: {len(ALL_PERMS)}\n")
    for r in d["roles"]:
        print("=" * 78)
        print(f"{r['name'].upper()}  ({r['code']}) — {r['perm_count']} ruxsat — doira: {r['scope']}")
        print(f"  BOT ({len(r['bot'])}): " + " · ".join(r["bot"]))
        print(f"  WEB ({len(r['web'])}): " + " · ".join(r["web"]))
        print(f"  Vazifa tugmalari: " + ", ".join(r["task_buttons"]))
        cb = r["can_be"]
        print(f"  Unga vazifa berish mumkinmi: {'HA' if cb['bajaruvchi'] else 'YO`Q'} · "
              f"tekshiruvchi qilib tayinlash: {'HA' if cb['tekshiruvchi'] else 'YO`Q'}")
    print("\n" + ("MENYU va ROUTE HIMOYASI MOS" if not d["problems"] else "NOMUVOFIQLIK:"))
    for p in d["problems"]:
        print("  ! " + p)
