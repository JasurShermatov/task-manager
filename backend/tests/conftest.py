import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DB = ROOT / "test_api.db"
if DB.exists():
    DB.unlink()
os.environ.setdefault("DATABASE_URL", f"sqlite:///{DB}")
os.environ.setdefault("SCHEDULER_ENABLED", "false")
os.environ.setdefault("REDIS_URL", "redis://127.0.0.1:1/0")
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("SERVICE_TOKEN", "test-service")
os.environ.setdefault("ADMIN_LOGIN", "boss")
os.environ.setdefault("ADMIN_PASSWORD", "boss12345")
os.environ.setdefault("UPLOAD_DIR", str(ROOT / "test_uploads"))
os.environ.setdefault("TZ_NAME", "Asia/Tashkent")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
       b"\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4"
       b"\x00\x00\x00\x00IEND\xaeB`\x82")


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


class U:
    """Tizimga kirgan foydalanuvchi."""

    def __init__(self, c, login, password):
        r = c.post("/auth/login", json={"login": login, "password": password})
        assert r.status_code == 200, r.text
        self.c = c
        data = r.json()
        self.tok = data["access_token"]
        self.refresh = data["refresh_token"]
        self.id = data["user"]["id"]
        self.role = data["user"]["role"]
        self.name = data["user"]["full_name"]

    def h(self, extra=None):
        d = {"Authorization": f"Bearer {self.tok}", "X-Source": "web"}
        if extra:
            d.update(extra)
        return d

    def get(self, p, **kw):
        return self.c.get(p, headers=self.h(), **kw)

    def post(self, p, json=None, **kw):
        return self.c.post(p, json=json if json is not None else {}, headers=self.h(), **kw)

    def patch(self, p, json):
        return self.c.patch(p, json=json, headers=self.h())

    def delete(self, p):
        return self.c.delete(p, headers=self.h())

    def upload(self, p, files, data=None):
        return self.c.post(p, files=files, data=data or {}, headers=self.h())

    def prove(self, task_id, name="dalil.jpg"):
        """Dalil biriktiradi — topshirishdan oldin shart."""
        return self.upload(f"/tasks/{task_id}/files", files={"file": (name, PNG, "image/jpeg")},
                           data={"kind": "proof"})


@pytest.fixture(scope="session")
def boss(client):
    return U(client, "boss", "boss12345")


@pytest.fixture(scope="session")
def world(client, boss):
    """Bitta assistant, ikkita bo'lim boshlig'i va ikkita asosiy bo'lim xodimi."""
    deps = {}
    for nm in ("Ta'minot", "Qurilish"):
        r = boss.post("/departments", json={"name": nm})
        assert r.status_code == 201, r.text
        deps[nm] = r.json()

    def mk(login, full_name, role, **kw):
        r = boss.post("/users", json={"full_name": full_name, "login": login, "password": "parol123",
                                      "role": role, **kw})
        assert r.status_code == 201, r.text
        return r.json()

    made = {
        "assistant": mk("assistant", "Assistant Aliyev", "assistant"),
        "head1": mk("head1", "Sanjar Ergashev", "bolim_boshligi", department_id=deps["Ta'minot"]["id"]),
        "head2": mk("head2", "Bekzod Qodirov", "bolim_boshligi", department_id=deps["Qurilish"]["id"]),
        "worker1": mk("worker1", "Rustam Yusupov", "ijrochi", position="Buxgalter"),
        "worker2": mk("worker2", "Dilshod Nazarov", "ijrochi", position="Ta'minotchi"),
    }
    return {"departments": deps, "users": made}


@pytest.fixture(scope="session")
def users(client, world):
    return {k: U(client, k, "parol123") for k in ("assistant", "head1", "head2", "worker1", "worker2")}
