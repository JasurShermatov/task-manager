"""Bitta tokenga bitta bot.

Ikkinchi nusxa ishga tushsa Telegram yangilanishlarni ikkiga bo'lib yuboradi va odam
«kod noto'g'ri» / «hisob bog'lanmagan» xabarlarini ko'radi — foydalanuvchi uchun bu
«bot uzilib qoldi» bo'lib ko'rinadi. Ijozat shu holatning oldini oladi.
"""
from datetime import datetime, timedelta

from app.db import SessionLocal
from app.models import AppSetting

H = {"X-Service-Token": "test-service"}


def _lease(client, who: str) -> dict:
    r = client.post("/telegram/bot-lease", json={"instance_id": who}, headers=H)
    assert r.status_code == 200, r.text
    return r.json()


def _age_the_lease(seconds: int):
    db = SessionLocal()
    row = db.get(AppSetting, "bot_lease")
    holder = (row.value or "").split("|", 1)[0]
    row.value = f"{holder}|{(datetime.utcnow() - timedelta(seconds=seconds)).isoformat(timespec='seconds')}"
    db.commit()
    db.close()


def test_first_bot_works_and_the_second_waits(client):
    assert _lease(client, "server:1")["granted"] is True
    second = _lease(client, "local:2")
    assert second["granted"] is False, "ikkinchi nusxa ham ishlab ketsa xabarlar ikkiga bo'linadi"
    assert second["holder"] == "server:1", "kim ushlab turganini aytishi kerak"
    assert _lease(client, "server:1")["granted"] is True, "ishlab turgani ijozatini yangilay olsin"


def test_a_dead_bot_does_not_block_forever(client):
    """Server boti o'chsa, ikkinchisi TTL o'tgach o'zi ishga tushadi — qo'lda hech narsa
    qilinmaydi. Aks holda bot butunlay yo'qolib qolardi."""
    _lease(client, "server:1")
    _age_the_lease(200)
    assert _lease(client, "local:2")["granted"] is True


def test_instance_id_is_required(client):
    assert client.post("/telegram/bot-lease", json={}, headers=H).status_code == 422


def test_lease_needs_the_service_token(client):
    assert client.post("/telegram/bot-lease", json={"instance_id": "x"}).status_code == 401
