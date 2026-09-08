"""Thin async client for the SAFF API. Every call acts on behalf of a linked user (X-Acting-User-Id)."""
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
        try:
            r = await self.c.request(method, path, headers=self._h(user_id), **kw)
        except httpx.HTTPError as e:
            raise ApiError(0, "NETWORK", f"API bilan aloqa yo'q: {e.__class__.__name__}")
        if r.status_code >= 400:
            try:
                d = r.json()
            except Exception:
                d = {"code": "HTTP", "message": r.text[:200]}
            raise ApiError(r.status_code, d.get("code", "ERROR"), d.get("message", ""), d)
        if r.status_code == 204 or not r.content:
            return None
        return r.json()

    # --- service ---
    async def user_by_tg(self, tg_id: int) -> Optional[dict]:
        try:
            return await self._req("GET", f"/telegram/user-by-tg/{tg_id}")
        except ApiError as e:
            if e.status == 404:
                return None
            raise

    async def consume_code(self, code: str, tg_id: int) -> dict:
        return await self._req("POST", "/telegram/consume-code", json={"code": code, "telegram_user_id": tg_id})

    async def outbox(self) -> list:
        return await self._req("GET", "/telegram/outbox", params={"limit": 50})

    async def outbox_ack(self, sent: list, failed: list):
        return await self._req("POST", "/telegram/outbox/ack", json={"sent": sent, "failed": failed})

    async def register_username(self, username: str) -> dict:
        return await self._req("POST", "/telegram/register-username", json={"username": username})

    async def sign_file(self, att_id: int) -> dict:
        return await self._req("GET", f"/files/{att_id}/sign")

    # --- acting as user ---
    async def me(self, uid): return await self._req("GET", "/auth/me", uid)
    async def tasks(self, uid, **params): return await self._req("GET", "/tasks", uid, params={k: v for k, v in params.items() if v is not None})
    async def task(self, uid, tid): return await self._req("GET", f"/tasks/{tid}", uid)
    async def task_by_code(self, uid, code): return await self._req("GET", f"/tasks/by-code/{code}", uid)
    async def create_task(self, uid, body): return await self._req("POST", "/tasks", uid, json=body)
    async def start(self, uid, tid): return await self._req("POST", f"/tasks/{tid}/start", uid)
    async def submit_review(self, uid, tid): return await self._req("POST", f"/tasks/{tid}/submit-review", uid)
    async def accept(self, uid, tid): return await self._req("POST", f"/tasks/{tid}/accept", uid, json={})
    async def return_task(self, uid, tid, reason): return await self._req("POST", f"/tasks/{tid}/return", uid, json={"reason": reason})
    async def block(self, uid, tid, reason, note): return await self._req("POST", f"/tasks/{tid}/block", uid, json={"reason": reason, "note": note})
    async def unblock(self, uid, tid): return await self._req("POST", f"/tasks/{tid}/unblock", uid)
    async def checklist_set(self, uid, tid, items): return await self._req("PATCH", f"/tasks/{tid}/checklist", uid, json={"items": items})
    async def daily(self, uid, tid, body): return await self._req("POST", f"/tasks/{tid}/daily-progress", uid, json=body)
    async def comment(self, uid, tid, text): return await self._req("POST", f"/tasks/{tid}/comments", uid, json={"text": text})
    async def upload(self, uid, tid, data: bytes, filename: str, mime: str, kind: str, daily_id=None):
        form = {"kind": kind}
        if daily_id:
            form["daily_progress_id"] = str(daily_id)
        return await self._req("POST", f"/tasks/{tid}/attachments", uid, files={"file": (filename, data, mime)}, data=form)
    async def projects(self, uid): return await self._req("GET", "/projects", uid)
    async def locations(self, uid, project_id): return await self._req("GET", "/locations", uid, params={"project_id": project_id})
    async def users(self, uid, project_id=None, role=None):
        return await self._req("GET", "/users", uid, params={k: v for k, v in {"project_id": project_id, "role": role}.items() if v})
    async def task_types(self, uid): return await self._req("GET", "/task-types", uid)
    async def voice_task(self, uid, data: bytes, lang: str, project_id=None):
        form = {"lang": lang}
        if project_id:
            form["project_id"] = str(project_id)
        return await self._req("POST", "/ai/voice-task", uid, files={"file": ("voice.ogg", data, "audio/ogg")}, data=form)
    async def parse_task(self, uid, text: str, lang: str, project_id=None):
        return await self._req("POST", "/ai/parse-task", uid, json={"text": text, "lang": lang, "project_id": project_id})
    async def set_lang(self, uid, lang): return await self._req("PATCH", f"/users/{uid}", uid, json={"lang": lang})
    async def meta(self, uid): return await self._req("GET", "/meta", uid)
    async def summary(self, uid, **params):
        return await self._req("GET", "/reports/summary", uid, params={k: v for k, v in params.items() if v is not None})


api = Api()
