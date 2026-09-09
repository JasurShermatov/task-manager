import os
import pathlib
import socket
import subprocess
import sys
import time

import pytest

BOT = pathlib.Path(__file__).resolve().parents[1]
ROOT = BOT.parent
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BOT))
os.environ.setdefault("BOT_TOKEN", "123456:test-token")


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


@pytest.fixture(scope="session")
def live_api(tmp_path_factory):
    """Haqiqiy API'ni sqlite ustida ko'taradi va (base_url, boss tokeni) qaytaradi."""
    import httpx
    port = free_port()
    tmp = tmp_path_factory.mktemp("api")
    env = {**os.environ,
           "DATABASE_URL": f"sqlite:///{tmp / 'bot_api.db'}",
           "SCHEDULER_ENABLED": "false",
           "REDIS_URL": "redis://127.0.0.1:1/0",
           "JWT_SECRET": "bot-test",
           "SERVICE_TOKEN": "dev-service-token",
           "ADMIN_LOGIN": "boss", "ADMIN_PASSWORD": "boss12345",
           "UPLOAD_DIR": str(tmp / "uploads"),
           "PYTHONPATH": str(BACKEND)}
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port), "--log-level", "warning"],
        cwd=str(BACKEND), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{port}"
    for _ in range(80):
        try:
            if httpx.get(f"{base}/health", timeout=1).status_code == 200:
                break
        except Exception:
            time.sleep(0.25)
    else:
        out = proc.communicate(timeout=5)[0].decode()
        proc.kill()
        raise RuntimeError("API ko'tarilmadi:\n" + out)

    os.environ["SERVICE_TOKEN"] = "dev-service-token"
    os.environ["API_BASE_URL"] = base
    with httpx.Client(base_url=base, timeout=10) as c:
        tok = c.post("/auth/login", json={"login": "boss", "password": "boss12345"}).json()["access_token"]
    yield base, tok
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
