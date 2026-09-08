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
os.environ.setdefault("ADMIN_LOGIN", "admin")
os.environ.setdefault("ADMIN_PASSWORD", "admin12345")
os.environ.setdefault("UPLOAD_DIR", str(ROOT / "test_uploads"))

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


class U:
    """Logged-in user handle."""
    def __init__(self, c, login, password):
        r = c.post("/auth/login", json={"login": login, "password": password})
        assert r.status_code == 200, r.text
        self.c = c
        self.tok = r.json()["access_token"]
        self.refresh = r.json()["refresh_token"]
        me = self.get("/auth/me").json()
        self.id = me["user"]["id"]
        self.role = me["user"]["role"]["code"]
        self.perms = me["permissions"]

    def h(self, extra=None):
        d = {"Authorization": f"Bearer {self.tok}", "X-Source": "web"}
        if extra:
            d.update(extra)
        return d

    def get(self, p, **kw): return self.c.get(p, headers=self.h(), **kw)
    def post(self, p, json=None, **kw): return self.c.post(p, json=json if json is not None else {}, headers=self.h(), **kw)
    def patch(self, p, json): return self.c.patch(p, json=json, headers=self.h())
    def delete(self, p): return self.c.delete(p, headers=self.h())
    def upload(self, p, files, data=None): return self.c.post(p, files=files, data=data or {}, headers=self.h())


# ---------- umumiy dunyo: loyiha, joylar va har rol uchun foydalanuvchi ----------
@pytest.fixture(scope="session")
def admin(client):
    return U(client, "admin", "admin12345")


@pytest.fixture(scope="session")
def world(client, admin):
    """Creates project/locations/users once; returns handles."""
    roles = {r["code"]: r["id"] for r in admin.get("/roles").json()}
    pr = admin.get("/projects").json()[0]
    locs = admin.get("/locations", params={"project_id": pr["id"]}).json()
    block = next(l for l in locs if l["kind"] == "block")
    floors = [l for l in locs if l["kind"] == "floor"]

    # second project + block (for scope tests)
    pr2 = admin.post("/projects", json={"code": "SAFF-02", "name": "Ikkinchi obyekt"}).json()
    block2 = admin.post("/locations", json={"project_id": pr2["id"], "name": "B blok", "kind": "block"}).json()

    def mkuser(login, name, role, scope_type="system", scope_id=None):
        r = admin.post("/users", json={"full_name": name, "login": login, "password": "parol1234567",
                                       "role_id": roles[role], "scope_type": scope_type, "scope_id": scope_id})
        assert r.status_code == 201, r.text
        return r.json()

    mkuser("rahbar", "Rahbar Rahbarov", "rahbar", "project", pr["id"])
    mkuser("prorab", "Prorab Prorabov", "prorab", "location", block["id"])
    mkuser("ishchi", "Rustam Ergashev", "bajaruvchi")
    mkuser("ishchi2", "Sardor Karimov", "bajaruvchi")
    mkuser("qc", "Doniyor Toshmatov", "tekshiruvchi", "project", pr["id"])
    mkuser("kuzat", "Kuzatuvchi K", "kuzatuvchi", "project", pr["id"])
    mkuser("chet", "Chet Odam", "prorab", "location", block2["id"])

    types = admin.get("/task-types").json()
    beton = next(t for t in types if t["name"] == "Beton ishlari")
    umumiy = next(t for t in types if t["name"] == "Umumiy vazifa")
    return {"project": pr, "project2": pr2, "block": block, "floors": floors, "roles": roles,
            "beton": beton, "umumiy": umumiy}


@pytest.fixture(scope="session")
def users(client, world):
    return {k: U(client, k, "parol1234567") for k in ("rahbar", "prorab", "ishchi", "ishchi2", "qc", "kuzat", "chet")}
