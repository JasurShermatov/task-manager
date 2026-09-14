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
