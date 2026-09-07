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
