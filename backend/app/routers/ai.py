from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from ..auth import Ctx, get_ctx
from ..db import get_db
from ..schemas import ParsedTask, ParseTaskIn
from ..services import ai

router = APIRouter(prefix="/ai", tags=["ai"])


@router.post("/transcribe")
async def transcribe(file: UploadFile = File(...), lang: str = Form("uz"),
                     ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    ctx.require_manager()
    data = await file.read()
    _, vocab = ai.build_context(db, ctx.user)
    return {"text": ai.transcribe(data, file.filename or "voice.ogg", lang, vocab)}


@router.post("/parse-task", response_model=ParsedTask)
def parse_task(body: ParseTaskIn, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    ctx.require_manager()
    return ai.parse_task(db, ctx.user, body.text, body.lang)


@router.post("/voice-task", response_model=ParsedTask)
async def voice_task(file: UploadFile = File(...), lang: str = Form("uz"),
                     ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    """Bir qadamda: ovoz -> matn -> tuzilgan vazifa taklifi (hech narsa saqlanmaydi).
    Bazadagi haqiqiy ismlar ovoz tanishga lug'at bo'lib beriladi."""
    ctx.require_manager()
    data = await file.read()
    _, vocab = ai.build_context(db, ctx.user)
    text = ai.transcribe(data, file.filename or "voice.ogg", lang, vocab)
    return ai.parse_task(db, ctx.user, text, lang)
