"""Ovoz -> matn -> tuzilgan vazifa.

2.0 da model ishi ancha yengil: loyiha ham, ish turi ham yo'q. Topishi kerak bo'lgan narsa
uchta — **kim**, **nima**, **qachon**. Shuning uchun aniqlik 1.0 ga qaraganda yuqori.

Ikki joyda aniqlik oshiriladi:
  1. Ovoz tanishga bazadagi haqiqiy ismlar lug'at bo'lib beriladi (aks holda o'zbekcha ismlar
     noto'g'ri eshitiladi: "Akmal Sobirov" -> "Komil Sabirov").
  2. Modelga xodimlar ro'yxati id bilan beriladi va u ro'yxatdan tanlaydi, taxmin qilmaydi.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional

import httpx
from rapidfuzz import fuzz, process
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import clock
from ..config import settings
from ..errors import validation
from ..models import MANAGERS, NEW, PROGRESS, Department, Task, User
from ..roles import role_name

OPENAI_URL = "https://api.openai.com/v1"
CONFIDENT_SCORE = 85       # avtomatik tanlash uchun minimal ball
CONFIDENT_GAP = 10         # ikkinchi nomzoddan shuncha ball yuqori bo'lishi kerak
VOCAB_LIMIT = 700          # STT prompt uzunligi chegarasi

SYSTEM = """Sen qurilish kompaniyasi boshlig'ining yordamchisisan. Ovozdan yozilgan matndan
bitta vazifa ajratib olasan va faqat JSON qaytarasan.

Maydonlar:
  title       - qisqa, buyruq shaklida, 250 belgigacha. Ism va sanani sarlavhaga qo'shma.
  description - qo'shimcha tafsilot bo'lsa; bo'lmasa null.
  assignee_id - BERILGAN PEOPLE ro'yxatidan id. Ishonchli topa olmasang null qaytar, taxmin qilma.
  assignee_name_heard - matnda eshitilgan ism (bo'lmasa null).
  due_at      - "YYYY-MM-DD" yoki "YYYY-MM-DDTHH:MM". Aniq bo'lmasa null.

Muddat qoidalari (bugungi sana TODAY sifatida beriladi):
  "bugun"=TODAY, "ertaga"=TODAY+1, "indinga"=TODAY+2, "bu hafta"=shu hafta juma,
  "keyingi hafta"=keyingi hafta juma, "N kundan keyin"=TODAY+N, hafta kuni aytilsa - keyingi o'sha kun.
  Vaqt qismi ("kechgacha", "ertalab", "soat 3 gacha") SANANI o'zgartirmaydi:
  "ertaga kechgacha" = ertangi sana. Soat aniq aytilsa (masalan "soat 14 gacha") uni HH:MM ga qo'y,
  aks holda faqat sana qaytar.

Faqat JSON qaytar, boshqa matn yozma."""


# ---------------------------------------------------------------- OpenAI
def _key() -> str:
    if not settings.OPENAI_API_KEY:
        raise validation("VOICE_NOT_CONFIGURED",
                         "Ovozli kiritish sozlanmagan (OPENAI_API_KEY yo'q).")
    return settings.OPENAI_API_KEY


def transcribe(audio: bytes, filename: str = "voice.ogg", lang: str = "uz",
               vocab: Optional[list[str]] = None) -> str:
    prompt = "Qurilish kompaniyasi vazifalari."
    if vocab:
        joined = ", ".join(vocab)
        prompt += " Nomlar: " + joined[:VOCAB_LIMIT]
    with httpx.Client(timeout=120) as c:
        r = c.post(f"{OPENAI_URL}/audio/transcriptions",
                   headers={"Authorization": f"Bearer {_key()}"},
                   files={"file": (filename, audio, "application/octet-stream")},
                   data={"model": settings.OPENAI_STT_MODEL, "language": lang, "prompt": prompt})
    if r.status_code >= 400:
        raise validation("VOICE_FAILED", "Ovozni matnga o'girib bo'lmadi. Qayta urinib ko'ring.",
                         detail=r.text[:300])
    return (r.json().get("text") or "").strip()


def llm_extract(text: str, today: date, context: str = "") -> dict:
    body = {"model": settings.OPENAI_LLM_MODEL, "response_format": {"type": "json_object"},
            "temperature": 0,
            "messages": [{"role": "system", "content": SYSTEM},
                         {"role": "user", "content": f"TODAY={today.isoformat()}\n{context}\n\nMATN:\n{text}"}]}
    with httpx.Client(timeout=60) as c:
        r = c.post(f"{OPENAI_URL}/chat/completions",
                   headers={"Authorization": f"Bearer {_key()}"}, json=body)
    if r.status_code >= 400:
        raise validation("VOICE_FAILED", "Matnni tushunib bo'lmadi. Qayta urinib ko'ring.",
                         detail=r.text[:300])
    try:
        return json.loads(r.json()["choices"][0]["message"]["content"])
    except (KeyError, ValueError, IndexError):
        return {}


# ---------------------------------------------------------------- ism moslash
def _norm(s: str) -> str:
    """O'zbekcha yozuv farqlarini tekislaydi: o'/g' apostroflari, x/h, sh/ch."""
    s = (s or "").lower().strip()
    for a, b in (("ʻ", ""), ("’", ""), ("'", ""), ("`", ""), ("ў", "u"), ("қ", "q"), ("ғ", "g"), ("ҳ", "h")):
        s = s.replace(a, b)
    s = s.replace("sh", "s").replace("ch", "c").replace("x", "h")
    # "Rustamga", "Rustamni" kabi qo'shimchalar
    s = re.sub(r"(ga|ni|dan|da|ning|niki)\b", " ", s)
    return " ".join(re.sub(r"[^0-9a-zа-яё ]+", " ", s).split())


@dataclass
class Candidate:
    id: int
    full_name: str
    hint: str
    score: int


def assignable(db: Session, creator: User) -> list[User]:
    """Kimga vazifa berish mumkin: hamma faol xodim, o'zidan tashqari.
    Boss va assistant bir-biriga ham bera oladi — shuning uchun rol bo'yicha filtr yo'q."""
    return [u for u in db.scalars(select(User).where(User.is_active.is_(True)).order_by(User.full_name))
            if u.id != creator.id]


def user_hint(db: Session, u: User) -> str:
    """Bir xil ismli ikki odamni ajratish uchun: "Bo'lim boshlig'i · Ta'minot"."""
    parts = [role_name(u.role, "uz")]
    if u.department and u.department.name:
        parts.append(u.department.name)
    elif u.position:
        parts.append(u.position)
    return " · ".join(parts)


def _unique_hints(cands: list[Candidate], people: dict[int, User]) -> list[Candidate]:
    seen: dict[str, list[Candidate]] = {}
    for c in cands:
        seen.setdefault(f"{c.full_name}|{c.hint}", []).append(c)
    for group in seen.values():
        if len(group) > 1:
            for c in group:
                u = people.get(c.id)
                tail = (u.phone or "")[-4:] if u and u.phone else f"#{c.id}"
                c.hint = f"{c.hint} · {tail}" if c.hint else tail
    return cands


def match_users(db: Session, heard: str, creator: User) -> tuple[list[Candidate], bool]:
    """(nomzodlar, ishonchlimi). Ishonchli bo'lsa birinchisi avtomatik tanlanadi."""
    people = {u.id: u for u in assignable(db, creator)}
    if not people or not (heard or "").strip():
        return [], False
    keys = {u.id: _norm(u.full_name) for u in people.values()}
    q = _norm(heard)
    if not q:
        return [], False
    scored = []
    for uid, key in keys.items():
        score = max(fuzz.WRatio(q, key), fuzz.partial_ratio(q, key),
                    max((fuzz.ratio(q, part) for part in key.split()), default=0))
        scored.append((score, uid))
    scored.sort(reverse=True)
    top = [s for s in scored if s[0] >= 60][:5]
    cands = [Candidate(id=uid, full_name=people[uid].full_name, hint=user_hint(db, people[uid]),
                       score=int(score)) for score, uid in top]
    cands = _unique_hints(cands, people)
    confident = bool(cands) and cands[0].score >= CONFIDENT_SCORE and (
        len(cands) == 1 or cands[0].score - cands[1].score >= CONFIDENT_GAP)
    return cands, confident


# ---------------------------------------------------------------- kontekst
def build_context(db: Session, creator: User) -> tuple[str, list[str]]:
    people = assignable(db, creator)
    lines = [f"- id={u.id} | {u.full_name}"
             + (f" | {u.position}" if u.position else "")
             + (f" | {u.department.name}" if u.department else "")
             for u in people]
    ctx = "PEOPLE (assignee_id shu ro'yxatdan tanlanadi):\n" + "\n".join(lines[:120])
    vocab = [u.full_name for u in people]
    return ctx, vocab


# ---------------------------------------------------------------- asosiy
def parse_task(db: Session, creator: User, text: str, lang: str = "uz") -> dict:
    text = (text or "").strip()
    if not text:
        raise validation("EMPTY_TEXT", "Matn bo'sh.")
    ctx, _ = build_context(db, creator)
    data = llm_extract(text, clock.today(), ctx)
    warnings: list[str] = []

    title = (data.get("title") or text)[:250].strip()
    description = (data.get("description") or None)
    heard = (data.get("assignee_name_heard") or "").strip() or None

    # 1) model tanlagan id ishonchli bo'lsa - shuni olamiz
    assignee_id = None
    candidates: list[Candidate] = []
    raw_id = data.get("assignee_id")
    if isinstance(raw_id, int):
        u = db.get(User, raw_id)
        if u and u.is_active and u.id != creator.id:
            assignee_id = u.id
    # 2) aks holda eshitilgan ismni o'zimiz qidiramiz
    if not assignee_id and heard:
        candidates, confident = match_users(db, heard, creator)
        if confident:
            assignee_id = candidates[0].id
        elif candidates:
            warnings.append("ambiguous_assignee")
    if not assignee_id and not candidates:
        warnings.append("no_assignee")

    due = clock.parse_due(data.get("due_at"))
    if not due:
        warnings.append("no_deadline")

    if assignee_id and not candidates:
        u = db.get(User, assignee_id)
        candidates = [Candidate(id=u.id, full_name=u.full_name, hint=user_hint(db, u), score=100)]

    return {
        "transcript": text, "title": title, "description": description,
        "due_at": due.isoformat(timespec="minutes") if due else None,
        "assignee_id": assignee_id, "assignee_name_heard": heard,
        "assignee_candidates": [c.__dict__ for c in candidates],
        "warnings": warnings,
    }
