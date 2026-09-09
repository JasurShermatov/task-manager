"""Matn va tugmalar: uch tilda to'liqlik, kartochka, tahrirlash bloki, sana o'qish."""
import os
import sys
from datetime import date, datetime, timedelta

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("BOT_TOKEN", "123456:test-token")

import render  # noqa: E402
from i18n import ROLE, STATUS, T, field_of, role_label, status_label, t  # noqa: E402

D = lambda n: (datetime.now() + timedelta(days=n)).replace(microsecond=0).isoformat()  # noqa: E731

TASK = {
    "id": 7, "code": "V-1042", "title": "Ombor hisobotini tayyorlash", "status": "progress",
    "assignee_name": "Sanjar Ergashev", "department_name": "Ta'minot",
    "due_at": "2026-09-10T18:00:00", "is_late": False, "late_days": 0, "late_hours": 0,
    "return_count": 0, "proof_count": 0, "description": None, "submit_note": None,
    "permissions": {"start": True, "submit": True, "accept": False, "return": False},
}


# ---------------------------------------------------------------- i18n
def test_all_languages_have_every_key():
    base = set(T["uz"])
    for lang in ("ru", "en"):
        missing = base - set(T[lang])
        assert not missing, f"{lang} da yo'q: {sorted(missing)}"
        extra = set(T[lang]) - base
        assert not extra, f"{lang} da ortiqcha: {sorted(extra)}"


def test_placeholders_match_across_languages():
    import re
    ph = lambda s: set(re.findall(r"{(\w+)}", s))  # noqa: E731
    for key, uz in T["uz"].items():
        for lang in ("ru", "en"):
            assert ph(uz) == ph(T[lang][key]), f"{key} ({lang}) o'rin egallovchilari mos emas"


def test_every_status_and_role_has_a_label():
    for lang in ("uz", "ru", "en"):
        for s in ("new", "progress", "submitted", "done", "cancelled"):
            assert status_label(lang, s) != s, f"{lang}/{s}"
        for r in ("boss", "assistant", "bolim_boshligi", "ijrochi"):
            assert role_label(lang, r) != r, f"{lang}/{r}"
        assert set(STATUS[lang]) == set(STATUS["uz"])
        assert set(ROLE[lang]) == set(ROLE["uz"])


# ---------------------------------------------------------------- menyu
def test_menu_differs_by_role():
    boss = set(render.menu_keys("uz", "boss"))
    worker = set(render.menu_keys("uz", "ijrochi"))
    assert t("uz", "btn_new") in boss and t("uz", "btn_report") in boss
    assert t("uz", "btn_report") not in worker and t("uz", "btn_new") not in worker
    assert worker == {t("uz", "btn_my"), t("uz", "btn_submit"), t("uz", "btn_lang")}
    assert render.menu_keys("uz", "assistant") == render.menu_keys("uz", "boss"), \
        "assistant boshliq bilan teng"
    assert render.menu_keys("uz", "bolim_boshligi") == render.menu_keys("uz", "ijrochi")


def test_managers_can_also_submit_their_own_tasks():
    """Boshliq bilan assistant bir-biriga vazifa beradi — demak ularda ham
    «Vazifalarim» va «Topshirish» bo'lishi shart, aks holda o'z ishini yopa olmaydi."""
    boss = set(render.menu_keys("uz", "boss"))
    assert t("uz", "btn_my") in boss and t("uz", "btn_submit") in boss


def test_menu_rows_are_pairs():
    kb = render.main_menu("uz", "boss")
    assert all(len(r) <= 2 for r in kb.keyboard)
    assert sum(len(r) for r in kb.keyboard) == len(render.menu_keys("uz", "boss"))


# ---------------------------------------------------------------- kartochka
def test_task_card_shows_the_essentials():
    card = render.task_card("uz", TASK)
    assert "V-1042" in card and "Ombor hisobotini" in card and "Sanjar Ergashev" in card
    assert "10.09.2026 18:00" in card, "muddat soati bilan ko'rinishi kerak"
    assert "kechikdi" not in card


def test_late_task_is_marked():
    card = render.task_card("uz", {**TASK, "is_late": True, "late_days": 3, "late_hours": 74})
    assert "3 kun kechikdi" in card
    card_h = render.task_card("uz", {**TASK, "is_late": True, "late_days": 0, "late_hours": 5})
    assert "5 soat kechikdi" in card_h


def test_card_shows_returns_and_proofs():
    card = render.task_card("uz", {**TASK, "return_count": 2, "proof_count": 3,
                                   "submit_note": "Bajarildi"})
    assert "2 marta qaytarilgan" in card and "3 ta dalil" in card and "Bajarildi" in card


def test_task_buttons_follow_permissions():
    datas = [b.callback_data for row in render.task_kb("uz", TASK).inline_keyboard for b in row]
    assert "t:start:7" in datas and "t:sub:7" in datas
    assert not any(d.startswith("t:acc") for d in datas)
    mgr = render.task_kb("uz", {**TASK, "permissions": {"accept": True, "return": True}})
    datas = [b.callback_data for row in mgr.inline_keyboard for b in row]
    assert "t:acc:7" in datas and "t:ret:7" in datas


# ---------------------------------------------------------------- tahrirlash bloki
def test_task_block_round_trips():
    from main import parse_block
    d = {"title": "Devorlarni suvash", "assignee_name": "Rustam Ergashev",
         "due_at": "2026-09-12T14:00", "description": "Ikki qavat"}
    for lang in ("uz", "ru", "en"):
        block = render.task_block(lang, d)
        f = parse_block(block)
        assert set(f) == set(render.BLOCK_ORDER), f"{lang}: {sorted(f)}"
        assert f["title"] == "Devorlarni suvash"
        assert f["assignee"] == "Rustam Ergashev"
        assert f["due"] == "12.09.2026 14:00"


def test_edit_block_has_a_copy_button():
    block = render.task_block("uz", {"title": "Qisqa", "assignee_name": "Sanjar",
                                     "due_at": "2026-09-12T18:00"})
    assert len(block) <= render.COPY_LIMIT
    kb = render.edit_block_kb("uz", block)
    copy = [b for row in kb.inline_keyboard for b in row if getattr(b, "copy_text", None)]
    assert copy and copy[0].copy_text.text == block
    long_kb = render.edit_block_kb("uz", "x" * (render.COPY_LIMIT + 1))
    assert not [b for row in long_kb.inline_keyboard for b in row if getattr(b, "copy_text", None)]


def test_parser_understands_translated_keys():
    from main import parse_block
    f = parse_block("Kimga: Rustam Ergashev\nСрок: 15.09.2026\nDescription: birinchi qavat")
    assert f == {"assignee": "Rustam Ergashev", "due": "15.09.2026", "description": "birinchi qavat"}
    assert parse_block("Rustamga ertaga devor terishni ayting") == {}
    assert parse_block("Muddat: ertaga") == {"due": "ertaga"}
    assert field_of("Bajaruvchi") == "assignee" and field_of("nimadir") is None


# ---------------------------------------------------------------- sana
def test_spoken_dates_resolve():
    from main import parse_due
    today = date.today()
    assert parse_due("bugun")[:10] == today.isoformat()
    assert parse_due("ertaga")[:10] == (today + timedelta(days=1)).isoformat()
    assert parse_due("ertaga kechgacha")[:10] == (today + timedelta(days=1)).isoformat()
    assert parse_due("завтра")[:10] == (today + timedelta(days=1)).isoformat()
    assert parse_due("3 kun")[:10] == (today + timedelta(days=3)).isoformat()
    assert parse_due("keyingi hafta")[:10] == (today + timedelta(days=7)).isoformat()
    assert parse_due("salom") is None


def test_dates_default_to_six_pm_and_keep_explicit_hours():
    from main import parse_due
    assert parse_due("15.09.2026").endswith("T18:00")
    assert parse_due("15.09.2026 14:30").endswith("T14:30")
    assert parse_due("ertaga 09:00").endswith("T09:00")
    assert parse_due("2026-09-15").endswith("T18:00")


# ---------------------------------------------------------------- xabarlar
def test_every_notification_event_renders_in_every_language():
    payloads = {
        "task_created": {"code": "V-1", "title": "Ish", "due_at": "2026-09-10T18:00",
                         "actor_name": "Boss"},
        "task_started": {"code": "V-1", "title": "Ish", "actor_name": "Sanjar"},
        "task_submitted": {"code": "V-1", "title": "Ish", "assignee_name": "Sanjar",
                           "department": "Ta'minot", "due_at": "2026-09-10T18:00",
                           "on_time": True, "proof_count": 2, "note": "Tayyor"},
        "task_accepted": {"code": "V-1", "title": "Ish", "actor_name": "Boss"},
        "task_returned": {"code": "V-1", "title": "Ish", "reason": "Rasm aniq emas"},
        "task_cancelled": {"code": "V-1", "title": "Ish", "reason": "kerak emas"},
        "task_unassigned": {"code": "V-1", "title": "Ish"},
        "due_changed": {"code": "V-1", "title": "Ish", "old_due": "2026-09-10T18:00",
                        "due_at": "2026-09-15T18:00"},
        "comment": {"code": "V-1", "title": "Ish", "actor_name": "Sanjar", "text": "Material yo'q"},
        "reminder": {"code": "V-1", "title": "Ish", "due_at": "2026-09-10T18:00", "overdue": False},
        "overdue_alert": {"code": "V-1", "title": "Ish", "assignee_name": "Sanjar",
                          "department": "Ta'minot", "due_at": "2026-09-10T18:00",
                          "late_days": 1, "late_hours": 26},
        "overdue_digest": {"count": 2, "items": [
            {"code": "V-1", "title": "Ish", "assignee_name": "Sanjar", "late_days": 2}]},
        "due_today": {"count": 1, "items": [
            {"code": "V-2", "title": "Boshqa", "assignee_name": "Bekzod",
             "due_at": "2026-09-10T18:00"}]},
    }
    for event, p in payloads.items():
        for lang in ("uz", "ru", "en"):
            text = render.notif_text(lang, event, p)
            assert text and "{" not in text, f"{event}/{lang}: {text}"
            assert len(text) < 4096


def test_submission_notification_carries_accept_buttons():
    kb = render.notif_kb("uz", "task_submitted", {"id": 9})
    datas = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert datas == ["t:acc:9", "t:ret:9"], "boshliq xabarning o'zidan qabul qila olishi kerak"
    kb2 = render.notif_kb("uz", "task_created", {"id": 9})
    datas2 = [b.callback_data for row in kb2.inline_keyboard for b in row]
    assert "t:sub:9" in datas2, "ijrochi xabardan darhol topshira olishi kerak"
    assert render.notif_kb("uz", "overdue_digest", {}) is None


def test_report_keyboard_marks_the_active_period():
    kb = render.report_kb("uz", "month")
    labels = [b.text for row in kb.inline_keyboard for b in row]
    assert any(x.startswith("• ") and "Oy" in x for x in labels)
    datas = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert "rep:week" in datas and "rep:dl:xlsx:month" in datas and "rep:dl:csv:month" in datas


def test_people_text_lists_open_and_late():
    text = render.people_text("uz", [
        {"full_name": "Sanjar Ergashev", "role": "bolim_boshligi", "department_name": "Ta'minot",
         "open_tasks": 3, "late_tasks": 1},
        {"full_name": "Rustam Yusupov", "role": "ijrochi", "department_name": None,
         "open_tasks": 0, "late_tasks": 0}])
    assert "Sanjar Ergashev" in text and "Ta'minot" in text and "⏰ 1" in text
    assert "Rustam Yusupov" in text
