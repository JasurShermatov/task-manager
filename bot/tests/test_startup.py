"""Ishga tushishdagi xatolar tushunarli bo'lishi kerak.

Prodda shu chiqdi: token noto'g'ri bo'lganda bot 40 qatorlik traceback yozib o'lardi
va sabab ko'rinmasdi. Endi nima qilish kerakligi yoziladi.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("BOT_TOKEN", "123456:test-token")

import main as bot  # noqa: E402


@pytest.mark.asyncio
async def test_missing_token_explains_what_to_do(monkeypatch, caplog):
    monkeypatch.setattr(bot.settings, "BOT_TOKEN", "")
    with caplog.at_level("ERROR"):
        with pytest.raises(SystemExit):
            await bot.main()
    assert "BOT_TOKEN" in caplog.text
    assert "BotFather" in caplog.text, "qayerdan olish kerakligi aytilishi kerak"


@pytest.mark.asyncio
async def test_wrong_token_explains_what_to_do(monkeypatch, caplog):
    """Telegram «Unauthorized» desa — traceback emas, ko'rsatma chiqadi."""
    from aiogram.exceptions import TelegramUnauthorizedError

    monkeypatch.setattr(bot.settings, "BOT_TOKEN", "1234567890:AAHxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")

    async def boom(self, *a, **kw):
        raise TelegramUnauthorizedError(method=None, message="Unauthorized")

    async def close(self):
        return None

    monkeypatch.setattr(bot.Bot, "get_me", boom, raising=False)
    monkeypatch.setattr("aiogram.client.session.aiohttp.AiohttpSession.close", close, raising=False)
    with caplog.at_level("ERROR"):
        with pytest.raises(SystemExit):
            await bot.main()
    assert "BOT TOKENI NOTO'G'RI" in caplog.text
    assert "Revoke current token" in caplog.text
    assert "docker compose up -d --build bot" in caplog.text


@pytest.mark.asyncio
async def test_outbox_waits_quietly_while_api_is_down(monkeypatch, caplog):
    """API hali ko'tarilmagan bo'lsa bot log to'ldirmasligi kerak — jim kutadi."""
    import asyncio

    calls = {"n": 0}

    async def dead(*a, **kw):
        calls["n"] += 1
        raise ConnectionError("API yo'q")

    monkeypatch.setattr(bot.api, "outbox", dead)
    monkeypatch.setattr(bot.settings, "OUTBOX_INTERVAL", 0.01)
    with caplog.at_level("WARNING"):
        task = asyncio.create_task(bot.outbox_worker(object()))
        await asyncio.sleep(0.2)
        task.cancel()
    assert calls["n"] >= 2, "qayta urinishi kerak"
    assert caplog.text.count("API javob bermayapti") == 1, "har safar emas, bir marta yozilsin"
