from __future__ import annotations

from typing import Any, Optional

import httpx

from config import settings


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, data: dict | None = None):
        super().__init__(message)
        self.status, self.code, self.message, self.data = status, code, message, data or {}


class Api:
    def __init__(self):
        self.c = httpx.AsyncClient(base_url=settings.API_BASE_URL, timeout=60)

    def _h(self, user_id: Optional[int] = None) -> dict:
        h = {"X-Service-Token": settings.SERVICE_TOKEN, "X-Source": "bot"}
        if user_id:
            h["X-Acting-User-Id"] = str(user_id)
        return h

    async def _req(self, method: str, path: str, user_id: Optional[int] = None, **kw) -> Any:
        r = await self.c.request(method, path, headers=self._h(user_id), **kw)
        if r.status_code >= 400:
            try:
                body = r.json()
            except ValueError:
                body = {}
            raise ApiError(r.status_code, body.get("code", "ERROR"),
                           body.get("message", "Server xatosi."), body)
        if r.headers.get("content-type", "").startswith("application/json"):
            return r.json()
        return r.content

    # ---- kirish / bog'lash ----
    async def user_by_tg(self, tg_id: int) -> Optional[dict]:
        try:
            return await self._req("GET", f"/telegram/user-by-tg/{tg_id}")
        except ApiError as e:
            if e.status == 404:
                return None
            raise

    async def consume_code(self, code: str, tg_id: int) -> dict:
        return await self._req("POST", "/telegram/consume-code",
                               json={"code": code, "telegram_user_id": tg_id})

    async def register_username(self, username: str) -> dict:
        return await self._req("POST", "/telegram/register-username", json={"username": username})

    async def bot_lease(self, instance_id: str) -> dict:
        """Bitta tokenga bitta ishlaydigan bot — ijozatni API beradi."""
        return await self._req("POST", "/telegram/bot-lease", json={"instance_id": instance_id})

    async def link_revocations(self) -> list:
        """Web'da «Uzish» bosilgan (yoki odam bloklangan) telegram id'lar."""
        return await self._req("GET", "/telegram/link-revocations")

    async def outbox(self, limit: int = 50) -> list:
        return await self._req("GET", "/telegram/outbox", params={"limit": limit})

    async def outbox_ack(self, sent: list, failed: list):
        return await self._req("POST", "/telegram/outbox/ack", json={"sent": sent, "failed": failed})

    async def sign_file(self, file_id: int) -> dict:
        return await self._req("GET", f"/files/{file_id}/sign")

    # ---- foydalanuvchi ----
    async def me(self, uid):
        return await self._req("GET", "/auth/me", uid)

    async def set_lang(self, uid, lang):
        return await self._req("PATCH", "/auth/me", uid, json={"lang": lang})

    async def users(self, uid, **params):
        return await self._req("GET", "/users", uid,
                               params={k: v for k, v in params.items() if v is not None})

    # ---- vazifalar ----
    async def tasks(self, uid, **params):
        return await self._req("GET", "/tasks", uid,
                               params={k: v for k, v in params.items() if v is not None})

    async def task(self, uid, tid):
        return await self._req("GET", f"/tasks/{tid}", uid)

    async def task_by_code(self, uid, code):
        return await self._req("GET", f"/tasks/by-code/{code}", uid)

    async def create_task(self, uid, body):
        return await self._req("POST", "/tasks", uid, json=body)

    async def patch_task(self, uid, tid, body):
        return await self._req("PATCH", f"/tasks/{tid}", uid, json=body)

    async def start(self, uid, tid):
        return await self._req("POST", f"/tasks/{tid}/start", uid)

    async def submit(self, uid, tid, note):
        return await self._req("POST", f"/tasks/{tid}/submit", uid, json={"note": note})

    async def accept(self, uid, tid):
        return await self._req("POST", f"/tasks/{tid}/accept", uid)

    async def return_task(self, uid, tid, reason):
        return await self._req("POST", f"/tasks/{tid}/return", uid, json={"reason": reason})

    async def comment(self, uid, tid, text):
        return await self._req("POST", f"/tasks/{tid}/comments", uid, json={"text": text})

    async def upload(self, uid, tid, data: bytes, filename: str, mime: str, kind: str = "proof"):
        return await self._req("POST", f"/tasks/{tid}/files", uid,
                               files={"file": (filename, data, mime)}, data={"kind": kind})

    # ---- hisobot ----
    async def report(self, uid, period="month", role=None):
        return await self._req("GET", "/reports/bot-summary", uid,
                               params={k: v for k, v in {"period": period, "role": role}.items() if v})

    async def report_file(self, uid, period="month", fmt="xlsx") -> bytes:
        return await self._req("GET", "/reports/export", uid,
                               params={"period": period, "format": fmt})

    async def person_report(self, uid, user_id, period="month"):
        return await self._req("GET", f"/reports/person/{user_id}", uid, params={"period": period})

    async def dashboard(self, uid):
        return await self._req("GET", "/reports/dashboard", uid)

    # ---- ovoz ----
    async def voice_task(self, uid, data: bytes, lang: str):
        return await self._req("POST", "/ai/voice-task", uid,
                               files={"file": ("voice.ogg", data, "audio/ogg")}, data={"lang": lang})

    async def parse_task(self, uid, text: str, lang: str):
        return await self._req("POST", "/ai/parse-task", uid, json={"text": text, "lang": lang})


api = Api()
