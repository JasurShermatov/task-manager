from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, UploadFile, File, Form
from sqlalchemy.orm import Session

from ..auth import Ctx, get_ctx
from ..db import get_db
from ..schemas import ParseTaskIn, ParsedTask
from ..services import ai

router = APIRouter(prefix="/ai", tags=["ai"])


@router.post("/transcribe")
async def transcribe(file: UploadFile = File(...), lang: str = Form("uz"),
                     ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    ctx.require("tasks.create")
    data = await file.read()
    _, vocab = ai.build_context(db, ctx.user)
    return {"text": ai.transcribe(data, file.filename or "voice.ogg", lang, vocab)}


@router.post("/parse-task", response_model=ParsedTask)
def parse_task(body: ParseTaskIn, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    ctx.require("tasks.create")
    return ai.parse_task(db, ctx.user, body.text, body.project_id, body.lang)


@router.post("/voice-task", response_model=ParsedTask)
async def voice_task(file: UploadFile = File(...), lang: str = Form("uz"), project_id: Optional[int] = Form(None),
                     ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    """One shot: audio -> transcript -> structured task proposal (nothing is saved)."""
    ctx.require("tasks.create")
    data = await file.read()
    # bazadagi haqiqiy ism/obyekt nomlari ovoz tanishga beriladi - aks holda
    # o'zbekcha ismlar noto'g'ri eshitiladi ("Akmal Sobirov" -> "Komil Sabirov")
    _, vocab = ai.build_context(db, ctx.user)
    text = ai.transcribe(data, file.filename or "voice.ogg", lang, vocab)
    return ai.parse_task(db, ctx.user, text, project_id, lang)
