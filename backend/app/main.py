import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import inspect, text

from .config import settings
from .db import engine, SessionLocal, Base
from . import models  # noqa: F401  (register tables)
from .errors import ApiError
from .routers import admin, ai, auth, misc, reports, tasks
from .seed import seed

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("api")


LEGACY_TABLES = {"projects", "locations", "task_types", "task_templates", "roles",
                 "task_checklist_items", "task_daily_progress", "task_attachments",
                 "task_dependencies", "task_recurring_rules", "jobs"}
REQUIRED_USER_COLUMNS = {"role", "position", "department_id"}


def check_schema():
    """1.0 bazasi ustiga 2.0 ni ko'tarib bo'lmaydi.

    `create_all` faqat yo'q jadvalni yaratadi — mavjud jadvalga ustun qo'shmaydi. Shuning uchun
    eski baza qolgan bo'lsa, server "column users.department_id does not exist" deb yiqilardi.
    Bu yerda buni oldindan aniqlab, nima qilish kerakligini aniq aytamiz.
    """
    insp = inspect(engine)
    tables = set(insp.get_table_names())
    if "users" not in tables:
        return                      # bo'sh baza — create_all hammasini quradi
    missing = REQUIRED_USER_COLUMNS - {c["name"] for c in insp.get_columns("users")}
    legacy = tables & LEGACY_TABLES
    if not missing and not legacy:
        return
    log.error(
        "\n" + "=" * 72
        + "\nBAZA ESKI (1.0) — 2.0 ga mos emas."
        + (f"\n  yetishmayotgan ustunlar: {', '.join(sorted(missing))}" if missing else "")
        + (f"\n  eski jadvallar: {', '.join(sorted(legacy))}" if legacy else "")
        + "\n\n2.0 da ma'lumot tuzilmasi butunlay boshqacha (loyiha/joy/ish turi o'rniga"
        + "\nbo'lim va odam), shuning uchun bazani yangidan qurish kerak:"
        + "\n\n    docker compose run --rm api python -m app.reset_db --yes"
        + "\n    docker compose up -d"
        + "\n\nSinov ma'lumoti bilan to'ldirish:"
        + "\n    docker compose run --rm api python -m app.fake_data --reset"
        + "\n\nEski ma'lumot kerak bo'lsa avval zaxira oling:"
        + "\n    docker compose exec db pg_dump -U saff saff_tasks > saff-1.0-backup.sql"
        + "\n" + "=" * 72)
    raise SystemExit(1)


def init_db():
    """Jadvallarni yaratadi (Alembic ham bor; create_all birinchi ishga tushishni soddalashtiradi)."""
    for attempt in range(30):
        try:
            with engine.connect() as c:
                c.execute(text("SELECT 1"))
            break
        except Exception as e:  # pragma: no cover
            log.warning("DB not ready (%s), retry %d", e.__class__.__name__, attempt)
            time.sleep(2)
    check_schema()
    Base.metadata.create_all(engine)
    if engine.dialect.name == "postgresql":
        with engine.begin() as c:
            c.execute(text("CREATE SEQUENCE IF NOT EXISTS task_code_seq START 1000"))
            # Baza tashqaridan to'ldirilgan bo'lishi mumkin (fake_data, import, zaxiradan tiklash) -
            # ketma-ketlik ma'lumotdan orqada qolsa yangi vazifa kodi to'qnashadi. Har ko'tarilishda
            # uni eng katta mavjud koddan keyinga surib qo'yamiz.
            c.execute(text(
                "SELECT setval('task_code_seq', GREATEST(1000, COALESCE("
                "(SELECT MAX(CAST(SUBSTRING(code FROM 3) AS BIGINT)) FROM tasks "
                " WHERE code ~ '^V-[0-9]+$'), 0)))"))
    db = SessionLocal()
    try:
        seed(db)
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    sch = None
    if settings.SCHEDULER_ENABLED:
        from .services.scheduler import start_scheduler
        sch = start_scheduler(settings.TZ_NAME)
    yield
    if sch:
        sch.shutdown(wait=False)


app = FastAPI(title="SAFF Vazifalar API", version="2.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
                   expose_headers=["Content-Disposition"])


@app.middleware("http")
async def request_id_mw(request: Request, call_next):
    rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    request.state.request_id = rid
    resp = await call_next(request)
    resp.headers["X-Request-Id"] = rid
    return resp


@app.exception_handler(ApiError)
async def api_error_handler(request: Request, exc: ApiError):
    body = dict(exc.detail) if isinstance(exc.detail, dict) else {"code": "ERROR", "message": str(exc.detail), "field_errors": {}}
    body["request_id"] = getattr(request.state, "request_id", None)
    return JSONResponse(status_code=exc.status_code, content=body)


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    fe = {}
    for e in exc.errors():
        loc = [str(x) for x in e.get("loc", []) if x not in ("body", "query", "path")]
        fe[".".join(loc) or "_"] = e.get("msg", "invalid")
    return JSONResponse(status_code=422, content={"code": "VALIDATION", "message": "Ma'lumotlar noto'g'ri.",
                                                  "field_errors": fe, "request_id": getattr(request.state, "request_id", None)})


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    log.exception("unhandled error")
    return JSONResponse(status_code=500, content={"code": "INTERNAL", "message": "Server xatosi.", "field_errors": {},
                                                  "request_id": getattr(request.state, "request_id", None)})


for r in (auth.router, tasks.router, admin.router, reports.router, misc.router, ai.router):
    app.include_router(r)
