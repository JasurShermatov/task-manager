import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from .config import settings
from .db import engine, SessionLocal, Base
from . import models  # noqa: F401  (register tables)
from .errors import ApiError
from .routers import auth, tasks, admin, templates, reports, misc, ai
from .seed import seed

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("api")


def init_db():
    """Create tables (Alembic is also shipped; create_all keeps first run zero-config)."""
    for attempt in range(30):
        try:
            with engine.connect() as c:
                c.execute(text("SELECT 1"))
            break
        except Exception as e:  # pragma: no cover
            log.warning("DB not ready (%s), retry %d", e.__class__.__name__, attempt)
            time.sleep(2)
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


app = FastAPI(title="SAFF Vazifalar API", version="1.0.0", lifespan=lifespan)
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


for r in (auth.router, tasks.router, admin.router, templates.router, reports.router, misc.router, ai.router):
    app.include_router(r)
