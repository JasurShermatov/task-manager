"""Voice -> text -> structured task. Uses OpenAI REST via httpx (no SDK dependency)."""
from __future__ import annotations

import json
import re
from datetime import date, timedelta
from typing import Optional

import httpx
from rapidfuzz import fuzz, process
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import user_in_project
from ..config import settings
from ..errors import ApiError
from ..models import User, Project, Location, TaskType
from ..schemas import ParsedTask, Candidate

OPENAI = "https://api.openai.com/v1"


def _headers():
    if not settings.OPENAI_API_KEY:
        raise ApiError(503, "VOICE_NOT_CONFIGURED", "Ovozli kiritish sozlanmagan (OPENAI_API_KEY yo'q).")
    return {"Authorization": f"Bearer {settings.OPENAI_API_KEY}"}


LANG_HINT = {"uz": "O'zbek tilida (lotin), ruscha va inglizcha so'zlar aralash bo'lishi mumkin. Qurilish atamalari.",
             "ru": "Русский язык, возможны узбекские и английские слова. Строительные термины.",
             "en": "English, may contain Uzbek and Russian words. Construction terms."}


def transcribe(audio: bytes, filename: str, lang: str = "uz", vocab: Optional[list[str]] = None) -> str:
    """Ovozni matnga o'giradi. `vocab` - bazadagi haqiqiy ism, obyekt va ish turlari:
    ular prompt'ga qo'shilsa model o'zbekcha ismlarni ancha to'g'ri eshitadi
    ("Akmal Sobirov" ni "Komil Sabirov" deb yozib qo'ymaydi)."""
    hint = LANG_HINT.get(lang, LANG_HINT["uz"])
    if vocab:
        # OpenAI prompt ~224 token bilan cheklangan - eng kerakli so'zlarni sig'diramiz
        words, total = [], 0
        for w in vocab:
            if total + len(w) > 700:
                break
            words.append(w)
            total += len(w) + 2
        if words:
            hint += " Nomlar: " + ", ".join(words) + "."
    files = {"file": (filename, audio, "application/octet-stream")}
    data = {"model": settings.OPENAI_STT_MODEL, "prompt": hint, "response_format": "json"}
    if settings.OPENAI_STT_MODEL.startswith("whisper") and lang in ("uz", "ru", "en"):
        data["language"] = lang
    with httpx.Client(timeout=90) as c:
        r = c.post(f"{OPENAI}/audio/transcriptions", headers=_headers(), files=files, data=data)
    if r.status_code >= 400:
        raise ApiError(502, "STT_FAILED", f"Ovozni matnga o'tkazib bo'lmadi: {r.text[:200]}")
    return (r.json().get("text") or "").strip()


SYSTEM = """You extract a construction task from a manager's spoken instruction.

You are given the REAL lists of projects, work types and people from the database.
Pick from those lists by id - never invent an item that is not listed. If nothing in a
list clearly matches what was said, return null for that field (do NOT guess a close-looking one).

Return ONLY JSON with keys:
title (short task title in the SAME language as the instruction, max 120 chars; what must be done, not who),
description (details not captured elsewhere, or null),
priority ("low"|"normal"|"high"; only if urgency was actually said: shoshilinch/tezda/srochno/urgent -> high; otherwise "normal"),
planned_end (ISO date YYYY-MM-DD or null),
planned_start (ISO date or null; default null),
project_id (integer id from PROJECTS, or null),
type_id (integer id from WORK TYPES, or null),
assignee_name (the person's name exactly as written in PEOPLE if it clearly matches what was heard, otherwise the name as heard, or null),
location_name (block/floor/zone words as heard, or null),
quantity (number or null), unit (m3/m2/m/t/dona or null).

DEADLINES - resolve against TODAY, always return a real date:
  "bugun"/"сегодня"/"today" -> TODAY
  "ertaga"/"завтра"/"tomorrow" (also "ertaga kechgacha", "ertaga kechqurun", "ertagagacha") -> TODAY+1
  "indinga"/"послезавтра" -> TODAY+2
  "bu hafta"/"shu hafta oxirigacha" -> the coming Saturday
  "keyingi hafta" -> TODAY+7
  a weekday name ("jumagacha", "до пятницы") -> the next occurrence of that weekday
  "N kun(da/ichida)" -> TODAY+N
  a month named without a day ("oktabrgacha") -> the LAST day of that month; "oktabr boshigacha" -> the 1st.
The system stores dates only (no clock time), so "kechgacha"/"kechqurun"/"soat 12 gacha"
does not change the date - it still means that same day."""


def build_context(db: Session, creator: User) -> tuple[str, list[str]]:
    """Modelga beriladigan haqiqiy ro'yxatlar + ovoz tanishi uchun lug'at."""
    projects = [p for p in db.scalars(select(Project).where(Project.is_active == True))  # noqa
                if user_in_project(creator, p.id, db)]
    types = db.scalars(select(TaskType).where(TaskType.is_active == True)).all()  # noqa
    people = [u for u in db.scalars(select(User).where(User.is_active == True))  # noqa
              if "tasks.start" in (u.role.permissions_json or []) and u.id != creator.id]
    lines = ["PROJECTS:"] + [f"  {p.id} = {p.name}" for p in projects[:40]]
    lines += ["WORK TYPES:"] + [f"  {t.id} = {t.name}" for t in types[:40]]
    lines += ["PEOPLE:"] + [f"  {u.full_name}" for u in people[:60]]
    vocab = [p.name for p in projects[:15]] + [t.name for t in types[:12]] + [u.full_name for u in people[:40]]
    return "\n".join(lines), vocab


def llm_extract(text: str, today: date, lang: str, context: str = "") -> dict:
    user = (f"TODAY={today.isoformat()} (weekday {today.strftime('%A')}). UI language={lang}.\n"
            f"{context}\n\nInstruction: {text}")
    body = {"model": settings.OPENAI_LLM_MODEL, "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": SYSTEM},
                         {"role": "user", "content": user}]}
    with httpx.Client(timeout=60) as c:
        r = c.post(f"{OPENAI}/chat/completions", headers={**_headers(), "Content-Type": "application/json"}, json=body)
    if r.status_code >= 400:
        raise ApiError(502, "LLM_FAILED", f"Matnni tahlil qilib bo'lmadi: {r.text[:200]}")
    content = r.json()["choices"][0]["message"]["content"]
    try:
        return json.loads(content)
    except Exception:
        m = re.search(r"\{.*\}", content, re.S)
        return json.loads(m.group(0)) if m else {}


def _norm(s: str) -> str:
    s = s.lower().replace("’", "'").replace("‘", "'").replace("ʻ", "'")
    s = s.replace("o'", "o").replace("g'", "g").replace("x", "h").replace("q", "k").replace("sh", "s").replace("ch", "c")
    s = re.sub(r"(ov|ova|ev|eva|ovich|ovna|jon|bek|xon)\b", "", s)
    return re.sub(r"[^a-zа-я0-9 ]", "", s)


def user_hint(db: Session, u: User) -> str:
    """Bir xil ismli odamlarni ajratish uchun qisqa izoh: 'Prorab · B blok'.
    Doirasi bo'lmasa - hozir qaysi obyektda ishlayotgani olinadi."""
    where = ""
    if u.scope_type == "project":
        p = db.get(Project, u.scope_id) if u.scope_id else None
        where = p.name if p else ""
    elif u.scope_type == "location":
        loc = db.get(Location, u.scope_id) if u.scope_id else None
        where = loc.name if loc else ""
    if not where:
        from ..models import Task
        pid = db.execute(
            select(Task.project_id).where(Task.assignee_id == u.id, Task.is_active == True,  # noqa
                                          Task.status.in_(("plan", "progress", "review", "blocked")))
            .order_by(Task.updated_at.desc()).limit(1)).scalar()
        if pid:
            p = db.get(Project, pid)
            where = p.name if p else ""
    return " · ".join(x for x in (u.role.name, where) if x)


def _make_hints_unique(cands: list[Candidate], db: Session) -> None:
    """Ikki tugma bir xil ko'rinib qolmasligi kafolati - oxirgi chora sifatida
    telefon raqamining oxirgi 4 raqami qo'shiladi."""
    seen: dict[str, list[Candidate]] = {}
    for c in cands:
        seen.setdefault(f"{c.full_name}|{c.hint}", []).append(c)
    for group in seen.values():
        if len(group) < 2:
            continue
        for c in group:
            u = db.get(User, c.id)
            tail = (u.phone or "").strip()[-4:] if u and u.phone else ""
            c.hint = " · ".join(x for x in (c.hint, f"…{tail}" if tail else f"#{c.id}") if x)


def match_users(db: Session, heard: Optional[str], project_id: Optional[int], creator: User) -> tuple[list[Candidate], bool]:
    if not heard:
        return [], False
    users = db.scalars(select(User).where(User.is_active == True)).all()  # noqa
    # faqat ishni bajara oladigan odam taklif qilinadi - tekshiruvchi/kuzatuvchiga vazifa
    # berilsa u boshlay olmaydi va server baribir rad etadi
    users = [u for u in users if "tasks.start" in (u.role.permissions_json or []) and u.id != creator.id]
    if project_id:
        users = [u for u in users if user_in_project(u, project_id, db)]
    if not users:
        return [], False
    hn = _norm(heard)
    scored = []
    for u in users:
        cand = _norm(u.full_name)
        parts = cand.split()
        s1 = fuzz.token_set_ratio(hn, cand)
        s2 = fuzz.partial_ratio(hn, cand)
        s3 = max((fuzz.ratio(hn.split()[0] if hn.split() else hn, p) for p in parts), default=0)
        score = int(max(s1, (s2 + s3) / 2))
        scored.append((score, u))
    scored.sort(key=lambda x: -x[0])
    top = [Candidate(id=u.id, full_name=u.full_name, role=u.role.name, score=s, hint=user_hint(db, u))
           for s, u in scored[:3] if s >= 40]
    _make_hints_unique(top, db)
    # Bir xil (yoki juda yaqin) ismli ikki odam bo'lsa hech qachon o'zi tanlamaydi -
    # foydalanuvchiga tugmalar chiqadi. Ismlar bir xil bo'lsa farq 0 bo'ladi.
    confident = bool(top) and top[0].score >= 85 and (len(top) == 1 or top[0].score - top[1].score >= 10)
    return top, confident


def default_reviewer_id(db: Session, project_id: Optional[int], assignee_id: Optional[int],
                        creator: User) -> Optional[int]:
    """Kim tekshiradi: loyihaning tekshiruvchisi -> rahbari -> 'tasks.accept' huquqi bor boshqa odam.
    Huquqi yo'q odam (masalan prorab) tekshiruvchi qilib qo'yilsa vazifa tekshiruvda qotib qoladi."""
    users = [u for u in db.scalars(select(User).where(User.is_active == True))  # noqa
             if "tasks.accept" in (u.role.permissions_json or []) and u.id != assignee_id]
    if project_id:
        users = [u for u in users if user_in_project(u, project_id, db)]
    if not users:
        return creator.id if "tasks.accept" in (creator.role.permissions_json or []) else None
    order = {"tekshiruvchi": 0, "rahbar": 1}
    users.sort(key=lambda u: (order.get(u.role.code, 2), u.id != creator.id))
    return users[0].id


def match_one(db: Session, heard: Optional[str], rows, key="name", threshold=70):
    if not heard or not rows:
        return None
    names = {r.id: getattr(r, key) for r in rows}
    best = process.extractOne(heard, names, scorer=fuzz.WRatio)
    if best and best[1] >= threshold:
        return best[2]
    return None


def parse_task(db: Session, creator: User, text: str, project_id: Optional[int], lang: str) -> ParsedTask:
    if not settings.OPENAI_API_KEY:
        raise ApiError(503, "VOICE_NOT_CONFIGURED", "Ovozli/matnli tahlil sozlanmagan (OPENAI_API_KEY yo'q).")
    today = date.today()
    context, _ = build_context(db, creator)
    data = llm_extract(text, today, lang, context)
    out = ParsedTask(transcript=text, title=(data.get("title") or text[:120]).strip(),
                     description=data.get("description"), priority=data.get("priority") if data.get("priority") in ("low", "normal", "high") else "normal")
    # dates
    for k in ("planned_start", "planned_end"):
        v = data.get(k)
        try:
            setattr(out, k, date.fromisoformat(v) if v else None)
        except Exception:
            pass
    if not out.planned_start:
        out.planned_start = today
    if not out.planned_end:
        out.planned_end = today + timedelta(days=3)
        out.warnings.append("no_deadline")
    if out.planned_end < out.planned_start:
        out.planned_start = out.planned_end
    # project - avval model ro'yxatdan tanlagan id, keyin nomi bo'yicha, keyin bitta bo'lsa o'zi
    projects = [p for p in db.scalars(select(Project).where(Project.is_active == True)) if user_in_project(creator, p.id, db)]  # noqa
    allowed_p = {p.id for p in projects}
    picked_p = data.get("project_id") if data.get("project_id") in allowed_p else None
    pid = (project_id or picked_p
           or match_one(db, data.get("project_name"), projects, threshold=75)
           # model nom bermagan bo'lsa - butun matndan qidiramiz ("Brilliant City'da" kabi)
           or match_one(db, text, projects, threshold=88)
           or (projects[0].id if len(projects) == 1 else None))
    if pid:
        p = db.get(Project, pid)
        out.project_id, out.project_name = p.id, p.name
    else:
        out.warnings.append("no_project")
    # location
    if out.project_id and data.get("location_name"):
        locs = db.scalars(select(Location).where(Location.project_id == out.project_id, Location.is_active == True)).all()  # noqa
        lid = match_one(db, data.get("location_name"), locs, threshold=75)
        if lid:
            loc = db.get(Location, lid)
            out.location_id, out.location_name = loc.id, loc.name
    # ish turi - model tanlagani ustun. Fuzzy chegara yuqori: "fasad ishlari" ni
    # "beton ishlari" ga o'xshatib yuborgandan ko'ra umumiy turni qo'ygan afzal.
    types = db.scalars(select(TaskType).where(TaskType.is_active == True)).all()  # noqa
    allowed_t = {t.id for t in types}
    tid = data.get("type_id") if data.get("type_id") in allowed_t else None
    if not tid:
        tid = match_one(db, data.get("work_type"), types, threshold=82) or match_one(db, out.title, types, threshold=82)
    if not tid and types:
        tid = next((t.id for t in types if (t.group_name or "").lower() in ("umumiy", "general", "общие")), types[0].id)
        out.warnings.append("type_guessed")
    if tid:
        tt = db.get(TaskType, tid)
        out.type_id, out.type_name = tt.id, tt.name
    # assignee
    out.assignee_name_heard = data.get("assignee_name")
    cands, conf = match_users(db, out.assignee_name_heard, out.project_id, creator)
    out.assignee_candidates, out.assignee_confident = cands, conf
    if conf:
        out.assignee_id = cands[0].id
    elif not cands:
        out.warnings.append("no_assignee")
    out.reviewer_id = default_reviewer_id(db, out.project_id, out.assignee_id, creator)
    if data.get("quantity"):
        out.description = (out.description or "") + f"\nHajm: {data.get('quantity')} {data.get('unit') or ''}".rstrip()
    return out
