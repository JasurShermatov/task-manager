"""Ovozli vazifa: xato sababi yo'qolib ketmasin.

Eng og'riqli holat shu edi — OpenAI nima deyayotgani hech qayerda yozilmasdi va botda
faqat «Qayta urinib ko'ring» chiqardi. Sabab ko'rinmasa, tuzatib ham bo'lmaydi.
"""
import httpx
import pytest

from app.errors import ApiError
from app.services import ai


def _resp(status: int, body: str = '{"error":{"message":"nimadir"}}') -> httpx.Response:
    return httpx.Response(status, text=body, request=httpx.Request("POST", "https://x"))


@pytest.mark.parametrize("status,expect", [
    (401, "kalit"),
    (403, "ruxsat"),
    (404, "model"),
    (429, "limit"),
    (500, "javob bermayapti"),
])
def test_each_openai_error_gets_its_own_explanation(status, expect):
    with pytest.raises(ApiError) as e:
        ai._fail("transcribe", _resp(status), "zaxira xabar")
    assert e.value.code == "VOICE_FAILED"
    assert expect in e.value.detail["message"].lower(), e.value.detail["message"]


def test_unknown_error_falls_back_but_keeps_the_body():
    with pytest.raises(ApiError) as e:
        ai._fail("transcribe", _resp(418, '{"error":"choynak"}'), "zaxira xabar")
    d = e.value.detail
    assert d["message"] == "zaxira xabar"
    assert "choynak" in d["detail"], "asl javob yo'qolmasligi kerak"
    assert d["http_status"] == 418


def test_the_reason_is_written_to_the_log(caplog):
    """Serverda `docker compose logs api` bilan sababni ko'rish mumkin bo'lsin."""
    with caplog.at_level("ERROR"):
        with pytest.raises(ApiError):
            ai._fail("transcribe", _resp(401, '{"error":{"message":"Invalid key"}}'), "zaxira")
    assert "Invalid key" in caplog.text and "401" in caplog.text


def test_silence_is_not_reported_as_a_failure(monkeypatch):
    """Bo'sh javob — ovozda gap yo'q degani, xizmat buzilgani emas."""
    class FakeClient:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def post(self, *a, **kw): return _resp(200, '{"text":"   "}')

    monkeypatch.setattr(ai.settings, "OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(ai.httpx, "Client", lambda **kw: FakeClient())
    with pytest.raises(ApiError) as e:
        ai.transcribe(b"audio")
    assert "eshitilmadi" in e.value.detail["message"]


def test_network_failure_says_so(monkeypatch):
    class Dead:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def post(self, *a, **kw): raise httpx.ConnectError("ulanmadi")

    monkeypatch.setattr(ai.settings, "OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(ai.httpx, "Client", lambda **kw: Dead())
    with pytest.raises(ApiError) as e:
        ai.transcribe(b"audio")
    assert "ulanib bo'lmadi" in e.value.detail["message"]


def test_missing_key_is_a_separate_case(monkeypatch):
    """Kalit yo'q bo'lsa bot «sozlanmagan» deb aytadi — bu xato emas, sozlama."""
    monkeypatch.setattr(ai.settings, "OPENAI_API_KEY", "")
    with pytest.raises(ApiError) as e:
        ai.transcribe(b"audio")
    assert e.value.code == "VOICE_NOT_CONFIGURED"
