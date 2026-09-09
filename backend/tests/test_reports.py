"""Hisobot: foiz, kechikish va eksport. Raqamlar o'zaro mos kelishi shart."""
import csv
import io
from datetime import date, timedelta

D = lambda n: (date.today() + timedelta(days=n)).isoformat()  # noqa: E731


def _flow(boss, users, world, who, *, due, accept=True, prove=True):
    t = boss.post("/tasks", json={"title": f"Hisobot uchun {who}",
                                  "assignee_id": world["users"][who]["id"], "due_at": due}).json()
    u = users[who]
    if prove:
        u.prove(t["id"])
        u.post(f"/tasks/{t['id']}/submit", {"note": "Tayyor"})
        if accept:
            boss.post(f"/tasks/{t['id']}/accept")
    return t


def test_buckets_add_up_to_the_total(boss, users, world):
    """berilgan = vaqtida + kechikib + bajarilmagan + jarayonda — hisobot o'zini tekshiradi."""
    _flow(boss, users, world, "worker1", due=D(3))            # vaqtida bajarilgan
    _flow(boss, users, world, "worker1", due=D(-2))           # kechikib bajarilgan
    _flow(boss, users, world, "worker1", due=D(-1), prove=False)   # bajarilmagan
    _flow(boss, users, world, "worker1", due=D(5), prove=False)    # jarayonda

    rep = boss.get("/reports/summary", params={"period": "month"}).json()
    row = next(r for r in rep["rows"] if r["user_id"] == world["users"]["worker1"]["id"])
    assert row["given"] == row["on_time"] + row["late_done"] + row["not_done"] + row["in_progress"]
    assert row["on_time"] >= 1 and row["late_done"] >= 1 and row["not_done"] >= 1
    t = rep["totals"]
    assert t["given"] == t["on_time"] + t["late_done"] + t["not_done"] + t["in_progress"]


def test_percent_matches_the_example_from_the_brief(boss, users, world):
    """PM misoli: 10 berildi, 7 vaqtida -> 70%."""
    who = "head2"
    for _ in range(7):
        _flow(boss, users, world, who, due=D(4))
    for _ in range(2):
        _flow(boss, users, world, who, due=D(-3))
    _flow(boss, users, world, who, due=D(-1), prove=False)

    rep = boss.get("/reports/summary", params={"period": "month"}).json()
    row = next(r for r in rep["rows"] if r["user_id"] == world["users"][who]["id"])
    assert row["given"] == 10, row
    assert row["on_time"] == 7 and row["late_done"] == 2 and row["not_done"] == 1
    assert row["percent"] == 70.0
    assert row["avg_late_days"] > 0, "kechikkanlarda o'rtacha kun ko'rsatilishi kerak"


def test_percent_is_plain_division(boss, users, world):
    """Foiz = vaqtida / berilgan. Vazifa soni o'zgarsa foiz ham o'zgaradi — oddiy matematika."""
    who = "head1"

    def row():
        return next(r for r in boss.get("/reports/summary").json()["rows"]
                    if r["user_id"] == world["users"][who]["id"])

    _flow(boss, users, world, who, due=D(4))       # kamida bitta vaqtida bajarilgan bo'lsin
    before = row()
    assert before["on_time"] >= 1 and before["percent"] > 0

    for _ in range(5):
        boss.post("/tasks", json={"title": "Yangi berilgan",
                                  "assignee_id": world["users"][who]["id"], "due_at": D(20)})
    after = row()
    assert after["given"] == before["given"] + 5
    assert after["on_time"] == before["on_time"], "yangi vazifa hali bajarilmagan"
    assert after["percent"] == round(after["on_time"] / after["given"] * 100, 1)
    assert after["percent"] < before["percent"], "berilgan ko'paydi, vaqtida o'zgarmadi — foiz tushadi"


def test_cancelled_tasks_do_not_count_against_anyone(boss, users, world):
    who = "worker2"
    before = next((r for r in boss.get("/reports/summary").json()["rows"]
                   if r["user_id"] == world["users"][who]["id"]), {"given": 0})["given"]
    t = boss.post("/tasks", json={"title": "Bekor bo'ladi", "assignee_id": world["users"][who]["id"],
                                  "due_at": D(2)}).json()
    boss.post(f"/tasks/{t['id']}/cancel", {"reason": "kerak emas"})
    after = next(r for r in boss.get("/reports/summary").json()["rows"]
                 if r["user_id"] == world["users"][who]["id"])["given"]
    assert after == before, "bekor qilingan vazifa odamning hisobiga yozilmasligi kerak"


def test_report_can_be_filtered_by_role_and_department(boss, world):
    heads = boss.get("/reports/summary", params={"role": "bolim_boshligi"}).json()["rows"]
    assert heads and all(r["role"] == "bolim_boshligi" for r in heads)
    dep = world["departments"]["Qurilish"]["id"]
    rows = boss.get("/reports/summary", params={"department_id": dep}).json()["rows"]
    assert rows and all(r["department_id"] == dep for r in rows)


def test_periods_are_supported(boss):
    for period in ("week", "month", "year"):
        r = boss.get("/reports/summary", params={"period": period})
        assert r.status_code == 200, r.text
        assert r.json()["date_from"] <= r.json()["date_to"]
    r = boss.get("/reports/summary", params={"period": "custom", "date_from": D(-30), "date_to": D(0)})
    assert r.status_code == 200
    assert boss.get("/reports/summary", params={"period": "haftalik"}).status_code == 422


def test_csv_export_opens_correctly_in_excel(boss):
    r = boss.get("/reports/export", params={"period": "month", "format": "csv"})
    assert r.status_code == 200
    assert "attachment" in r.headers["content-disposition"]
    assert r.content.startswith(b"\xef\xbb\xbf"), "BOM yo'q - Excel o'zbekcha harflarni buzadi"
    text = r.content.decode("utf-8-sig")
    rows = list(csv.reader(io.StringIO(text), delimiter=";"))
    header = next(r for r in rows if r and r[0] == "Kim")
    assert "Foiz %" in header and "Vaqtida" in header
    assert any(r and r[0] == "JAMI" for r in rows)


def test_xlsx_export_is_a_real_workbook(boss):
    """Fayl haqiqiy xlsx: zip ichida kutilgan qismlar bor va qiymatlar qayta o'qiladi."""
    import zipfile

    from app.services import xlsx

    r = boss.get("/reports/export", params={"period": "month", "format": "xlsx"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml")
    assert r.content[:2] == b"PK", "zip emas"
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        names = set(z.namelist())
    assert {"[Content_Types].xml", "_rels/.rels", "xl/workbook.xml",
            "xl/_rels/workbook.xml.rels", "xl/styles.xml",
            "xl/worksheets/sheet1.xml"} <= names

    rows = xlsx.read_values(r.content)
    assert rows[0][0].startswith("SAFF Vazifalar")
    assert rows[2][:2] == ["Kim", "Rol"]
    assert rows[2][-1] == "Foiz %"
    assert rows[-1][0] == "JAMI"
    body = [x for x in rows[3:-2] if x and x[0]]
    assert body, "hech kim chiqmadi"
    assert all(len(x) == len(rows[2]) for x in body), "ustunlar soni mos emas"


def test_xlsx_escapes_special_characters():
    """O'zbekcha apostrof va < & " belgilari faylni buzmasligi kerak."""
    from app.services import xlsx
    data = xlsx.write([["O'tkir <A&B> \"tirnoq\"", 5, 12.5]])
    assert xlsx.read_values(data)[0] == ["O'tkir <A&B> \"tirnoq\"", "5", "12.5"]


def test_xlsx_column_names():
    from app.services import xlsx
    assert [xlsx.col_name(n) for n in (1, 2, 26, 27, 28, 52)] == ["A", "B", "Z", "AA", "AB", "AZ"]


def test_bot_report_is_a_readable_table(boss):
    r = boss.get("/reports/bot-summary", params={"period": "month"}).json()
    assert "JAMI" in r["table"] and "%" in r["table"]
    lines = r["table"].splitlines()
    assert len(lines) >= 3
    assert len({len(x) for x in lines}) <= 3, "ustunlar tekislanmagan"


def test_person_view_lists_the_late_ones(boss, world):
    uid = world["users"]["head2"]["id"]
    r = boss.get(f"/reports/person/{uid}", params={"period": "month"}).json()
    assert r["user"]["full_name"] == "Bekzod Qodirov"
    assert r["stat"]["given"] >= 10
    assert all(x["late_days"] >= 0 for x in r["late"])
    assert len(r["late"]) >= 2


def test_dashboard_gives_the_home_screen_numbers(boss):
    d = boss.get("/reports/dashboard").json()
    for k in ("open_tasks", "late_tasks", "submitted_tasks", "due_today", "people", "departments"):
        assert isinstance(d[k], int), k
    assert 0 <= d["percent_this_month"] <= 100
    assert d["departments"] >= 2


def test_performers_cannot_export(users):
    assert users["head1"].get("/reports/export", params={"format": "csv"}).status_code == 403
    assert users["worker1"].get("/reports/dashboard").status_code == 403
