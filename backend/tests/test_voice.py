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


# ---------------------------------------------------------------- til kodi
class _Spy:
    """Yuborilgan so'rovlarni yozib boradi va tayyor javob qaytaradi."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.sent: list[dict] = []

    def __enter__(self): return self
    def __exit__(self, *a): return False

    def post(self, url, headers=None, files=None, data=None, **kw):
        self.sent.append(dict(data or {}))
        return self.responses.pop(0)


def _spy(monkeypatch, *responses) -> _Spy:
    spy = _Spy(*responses)
    monkeypatch.setattr(ai.settings, "OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(ai.httpx, "Client", lambda **kw: spy)
    return spy


def test_uzbek_goes_in_the_prompt_not_the_language_field(monkeypatch):
    """gpt-4o-transcribe "uz" kodini rad etadi. Til nomi so'rov matnida aytiladi —
    OpenAI'ning o'z maslahati, va aniqlikka ham yordam beradi."""
    spy = _spy(monkeypatch, _resp(200, '{"text":"Ombor hisobotini tayyorla"}'))
    assert ai.transcribe(b"audio", lang="uz") == "Ombor hisobotini tayyorla"
    sent = spy.sent[0]
    assert "language" not in sent, "uz parametr sifatida yuborilmasligi kerak"
    assert "o'zbek" in sent["prompt"]
    assert len(spy.sent) == 1, "bitta so'rov yetarli - qayta urinish bo'lmasin"


def test_russian_still_uses_the_language_field(monkeypatch):
    spy = _spy(monkeypatch, _resp(200, '{"text":"Готово"}'))
    ai.transcribe(b"audio", lang="ru")
    assert spy.sent[0]["language"] == "ru"


def test_a_rejected_language_is_retried_without_it(monkeypatch):
    """Modellar va ular qo'llaydigan tillar o'zgarib turadi. Kod rad etilsa,
    bir marta parametrsiz qaytariladi — foydalanuvchi xatoni umuman ko'rmaydi."""
    bad = _resp(400, '{"error":{"message":"Language code not recognized",'
                     '"param": "language","code":"invalid_value"}}')
    spy = _spy(monkeypatch, bad, _resp(200, '{"text":"Bajarildi"}'))
    assert ai.transcribe(b"audio", lang="ru") == "Bajarildi"
    assert len(spy.sent) == 2
    assert "language" in spy.sent[0] and "language" not in spy.sent[1]


def test_other_400_errors_are_not_retried(monkeypatch):
    """Faqat til kodi qayta uriniladi — qolgan xatolarda ikkinchi so'rov ortiqcha."""
    spy = _spy(monkeypatch, _resp(400, '{"error":{"message":"Unsupported file","param":"file"}}'))
    with pytest.raises(ApiError):
        ai.transcribe(b"audio", lang="ru")
    assert len(spy.sent) == 1


def test_names_from_the_database_are_given_to_the_model(monkeypatch):
    """Lug'at bo'lmasa o'zbekcha ismlar noto'g'ri eshitiladi."""
    spy = _spy(monkeypatch, _resp(200, '{"text":"ok"}'))
    ai.transcribe(b"audio", lang="uz", vocab=["Akmal Sobirov", "Dilshod Nazarov"])
    assert "Akmal Sobirov" in spy.sent[0]["prompt"]
