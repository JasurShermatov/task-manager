"""Kirish: login katta-kichik harfga qaramaydi.

Administratsiya loginni bazaga **kichik harfda** saqlaydi. Kirish esa aniq moslikni
tekshirardi — natijada telefonda birinchi harfi kattalashib ketgan odam parol to'g'ri
bo'lsa ham kira olmasdi va sabab hech qayerda ko'rinmasdi.
"""


def _login(client, login, password="parol123"):
    return client.post("/auth/login", json={"login": login, "password": password})


def test_login_ignores_case_and_spaces(client, boss, world):
    """Bir xil odam, uch xil yozuv — uchalasi ham kirishi kerak."""
    for typed in ("worker1", "Worker1", "WORKER1", "  worker1  "):
        r = _login(client, typed)
        assert r.status_code == 200, f"{typed!r} bilan kira olmadi: {r.text}"
        assert r.json()["user"]["login"] == "worker1"


def test_a_new_login_is_saved_lowercase_and_still_works(boss, client):
    """Administratsiyada katta harf bilan yozilsa ham, kirish ishlashi kerak."""
    r = boss.post("/users", json={"full_name": "Katta Harf", "login": "  Katta.Harf  ",
                                  "password": "parol123", "role": "ijrochi"})
    assert r.status_code == 201, r.text
    assert r.json()["login"] == "katta.harf", "login kichik harfda saqlanadi"
    assert _login(client, "Katta.Harf").status_code == 200
    assert _login(client, "katta.harf").status_code == 200


def test_changing_the_login_does_not_lock_the_person_out(boss, client, world):
    """Aynan shu holat muammo bo'lgan edi: loginni o'zgartirgandan keyin kira olmaslik."""
    uid = world["users"]["worker2"]["id"]
    assert boss.patch(f"/users/{uid}", {"login": "Yangi.Login"}).status_code == 200
    assert _login(client, "Yangi.Login").status_code == 200
    assert _login(client, "yangi.login").status_code == 200


def test_password_change_takes_effect_at_once(boss, client, world):
    uid = world["users"]["worker2"]["id"]
    assert boss.post(f"/users/{uid}/password", {"password": "yangi456"}).status_code == 200
    assert _login(client, "yangi.login", "parol123").status_code == 401, "eski parol ishlamasin"
    assert _login(client, "Yangi.Login", "yangi456").status_code == 200


def test_wrong_password_is_still_refused(client, world):
    assert _login(client, "worker1", "boshqa-parol").status_code == 401


# ---------------------------------------------------------------- qulf va muddat
def test_brute_force_is_locked_after_five_tries(client, boss):
    """Himoya ishlashi kerak: ketma-ket xato urinishdan keyin qulf."""
    boss.post("/users", json={"full_name": "Qulf Sinovi", "login": "qulf1",
                              "password": "parol123", "role": "ijrochi"})
    for _ in range(5):
        assert _login(client, "qulf1", "xato").status_code == 401
    r = _login(client, "qulf1", "parol123")
    assert r.status_code == 429 and r.json()["code"] == "TOO_MANY_ATTEMPTS", r.text


def test_a_new_password_unlocks_the_person_at_once(client, boss):
    """Aynan shu joyda odam qoqilardi: boshliq yangi parol qo'yadi, lekin qulf
    tufayli odam yana 15 daqiqa kira olmaydi va sababini bilmaydi."""
    uid = boss.post("/users", json={"full_name": "Qulf Ikki", "login": "qulf2",
                                    "password": "parol123", "role": "ijrochi"}).json()["id"]
    for _ in range(5):
        _login(client, "qulf2", "xato")
    assert _login(client, "qulf2", "parol123").status_code == 429

    assert boss.post(f"/users/{uid}/password", {"password": "yangi789"}).status_code == 200
    assert _login(client, "qulf2", "yangi789").status_code == 200, "qulf ochilmadi"


def test_login_still_works_when_redis_is_down(client, world, monkeypatch):
    """Urinishlar hisobi — himoya vositasi, kirishning sharti emas. Redis yiqilsa
    hamma tizimdan chiqib qolmasligi kerak."""
    from app import redis_client

    class Dead:
        def get(self, *a, **kw): raise RuntimeError("redis yo'q")
        def set(self, *a, **kw): raise RuntimeError("redis yo'q")
        def delete(self, *a, **kw): raise RuntimeError("redis yo'q")
        def scan_iter(self, *a, **kw): raise RuntimeError("redis yo'q")

    monkeypatch.setattr(redis_client, "rds", Dead())
    assert _login(client, "worker1").status_code == 200


def test_refresh_token_lasts_fifteen_days(client, world):
    from datetime import datetime

    from app.db import SessionLocal
    from app.models import RefreshToken

    tok = _login(client, "worker1").json()["refresh_token"]
    db = SessionLocal()
    row = db.query(RefreshToken).filter(RefreshToken.token == tok).one()
    days = (row.expires_at - datetime.utcnow()).days
    db.close()
    assert days == 14, f"15 kun kutilgan edi, {days + 1} chiqdi"   # 14 kun + qolgan soatlar
