"""Rollar kesimidagi panellar - kod bilan hujjat bir joyda turishi uchun.

role_matrix.py menyuni bot/render.py dan, web menyusini Layout.tsx dan, route himoyasini
App.tsx dan o'qiydi. Shu yerda esa natija kutilgan bilan bir xilligini qotiramiz: kimdir
menyuga tugma qo'shsa yoki ruxsatni o'zgartirsa - test darhol aytadi.
"""
import pathlib
import sys

import pytest

BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

pytestmark = pytest.mark.skipif(not (BACKEND.parent / "frontend").exists(),
                                reason="frontend papkasi yonida bo'lmasa o'tkazib yuboriladi")

EXPECTED_BOT = {
    # superadmin: kuzatadi va vazifa beradi - o'zi ijrochi/tekshiruvchi emas
    "admin": ["btn_new", "btn_overdue", "btn_blocked", "btn_reports", "btn_team",
              "btn_search", "btn_lang", "btn_help"],
    "rahbar": ["btn_my", "btn_report", "btn_review", "btn_new", "btn_problem", "btn_overdue",
               "btn_blocked", "btn_reports", "btn_search", "btn_lang", "btn_help"],
    "prorab": ["btn_my", "btn_report", "btn_new", "btn_problem", "btn_overdue", "btn_blocked",
               "btn_reports", "btn_search", "btn_lang", "btn_help"],
    "bajaruvchi": ["btn_my", "btn_report", "btn_problem", "btn_search", "btn_lang", "btn_help"],
    "tekshiruvchi": ["btn_my", "btn_review", "btn_overdue", "btn_blocked", "btn_reports",
                     "btn_search", "btn_lang", "btn_help"],
    "kuzatuvchi": ["btn_overdue", "btn_blocked", "btn_reports", "btn_search", "btn_lang", "btn_help"],
}

EXPECTED_WEB = {
    "admin": ["nav_tasks", "nav_table", "nav_reports", "nav_bulk", "nav_projects", "nav_templates",
              "nav_types", "nav_telegram", "nav_profile", "nav_staff", "nav_admin"],
    "rahbar": ["nav_tasks", "nav_table", "nav_reports", "nav_bulk", "nav_projects", "nav_templates",
               "nav_telegram", "nav_profile"],
    "prorab": ["nav_tasks", "nav_table", "nav_reports", "nav_projects", "nav_telegram", "nav_profile"],
    "bajaruvchi": ["nav_tasks", "nav_table", "nav_telegram", "nav_profile"],
    "tekshiruvchi": ["nav_tasks", "nav_table", "nav_reports", "nav_telegram", "nav_profile"],
    "kuzatuvchi": ["nav_tasks", "nav_table", "nav_reports", "nav_telegram", "nav_profile"],
}


@pytest.fixture(scope="module")
def matrix():
    import role_matrix
    return {r["code"]: r for r in role_matrix.build()["roles"]}, role_matrix.build()["problems"]


def test_menu_and_route_protection_agree(matrix):
    """Menyuda ko'rinmasa - manzilni qo'lda yozib ham kira olmaydi (hamma rol uchun)."""
    _, problems = matrix
    assert problems == [], problems


def test_bot_panels_per_role(matrix):
    roles, _ = matrix
    for code, keys in EXPECTED_BOT.items():
        assert roles[code]["bot_keys"] == keys, f"{code} bot menyusi o'zgargan"


def test_web_panels_per_role(matrix):
    roles, _ = matrix
    for code, keys in EXPECTED_WEB.items():
        assert roles[code]["web"] == keys, f"{code} web menyusi o'zgargan"


def test_only_superadmin_sees_staff_and_admin(matrix):
    roles, _ = matrix
    for code, r in roles.items():
        has = {"nav_staff", "nav_admin"} & set(r["web"])
        assert bool(has) == (code == "admin"), f"{code}: Xodimlar/Administratsiya ko'rinishi noto'g'ri"


def test_who_can_be_assignee_and_reviewer(matrix):
    """Ijro qila oladigan va qabul qila oladigan rollar - vazifa qotib qolmasligi uchun."""
    roles, _ = matrix
    doers = {c for c, r in roles.items() if r["can_be"]["bajaruvchi"]}
    accepters = {c for c, r in roles.items() if r["can_be"]["tekshiruvchi"]}
    assert doers == {"admin", "rahbar", "prorab", "bajaruvchi"}
    assert accepters == {"admin", "rahbar", "tekshiruvchi"}
    # tekshiruvchi ish bajarmaydi, kuzatuvchi umuman hech narsa qilmaydi
    assert not roles["tekshiruvchi"]["can_be"]["bajaruvchi"]
    assert roles["kuzatuvchi"]["task_buttons"] == {}
