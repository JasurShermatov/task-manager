"""Ovozli vazifa sozlanganini tekshiradi.

    docker compose -f docker-compose.prod.yml run --rm api python -m app.voice_check

Nimani tekshiradi va nima uchun:
  1. kalit bormi                -> yo'q bo'lsa bot "sozlanmagan" deydi;
  2. OpenAI javob beryaptimi    -> serverda internet yoki kalit muammosi shu yerda ko'rinadi;
  3. sozlangan modellar ro'yxatda bormi -> eng ko'p uchraydigan xato: kalit modelga
     kira olmaydi yoki model nomi eskirgan. Bunda bot faqat "Qayta urinib ko'ring"
     der edi, sabab esa ko'rinmasdi.
"""
from __future__ import annotations

import sys

import httpx

from .config import settings
from .services.ai import OPENAI_URL


def main() -> int:
    key = settings.OPENAI_API_KEY
    stt, llm = settings.OPENAI_STT_MODEL, settings.OPENAI_LLM_MODEL
    print(f"STT model : {stt}")
    print(f"LLM model : {llm}")
    if not key:
        print("\nXATO: OPENAI_API_KEY bo'sh. .env ga qo'ying va api'ni qayta ishga tushiring.")
        print("Ovozsiz qolgan hamma narsa ishlayveradi.")
        return 1
    print(f"Kalit     : {key[:7]}… ({len(key)} belgi)")

    try:
        r = httpx.get(f"{OPENAI_URL}/models", headers={"Authorization": f"Bearer {key}"}, timeout=30)
    except httpx.HTTPError as e:
        print(f"\nXATO: OpenAI ga ulanib bo'lmadi ({type(e).__name__}): {e}")
        print("Serverda tashqi internet bormi tekshiring:  curl -I https://api.openai.com")
        return 1

    if r.status_code == 401:
        print("\nXATO: kalit noto'g'ri yoki bekor qilingan (HTTP 401).")
        print("platform.openai.com -> API keys dan yangisini oling va .env ga qo'ying.")
        return 1
    if r.status_code >= 400:
        print(f"\nXATO: OpenAI HTTP {r.status_code}\n{r.text[:400]}")
        return 1

    names = {m.get("id") for m in r.json().get("data", [])}
    print(f"Ulanish   : OK ({len(names)} ta model ko'rinyapti)")

    bad = False
    for label, model in (("STT", stt), ("LLM", llm)):
        if model in names:
            print(f"  {label}: {model} — bor")
        else:
            bad = True
            near = sorted(n for n in names if n.startswith(model.split("-")[0]))[:6]
            print(f"  {label}: {model} — YO'Q. Shu kalit uchun mavjudlari: {', '.join(near) or '—'}")

    if bad:
        print("\nModel nomini .env dagi OPENAI_STT_MODEL / OPENAI_LLM_MODEL da to'g'rilang,")
        print("keyin:  docker compose -f docker-compose.prod.yml up -d api")
        return 1

    print("\nHammasi joyida — ovozli vazifa ishlashi kerak.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
