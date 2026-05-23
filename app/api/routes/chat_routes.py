"""Phase 37, step 37.15 — AI Research Chat API surface."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from app.chat.answer_modes import ALL_MODES
from app.chat.chat_service import ChatService
from app.database.connection import get_db_session

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.get("/modes")
def list_modes() -> dict[str, Any]:
    return {"status": "OK", "modes": list(ALL_MODES)}


@router.post("")
def chat(
    payload: dict[str, Any] = Body(default_factory=dict),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    question = payload.get("question", "")
    if not isinstance(question, str):
        raise HTTPException(status_code=400, detail="question must be a string.")
    symbol = payload.get("symbol")
    mode = payload.get("mode")
    manual_option_snapshot_id = payload.get("manual_option_snapshot_id")
    option_data_requested = bool(payload.get("option_data_requested", False))

    response = ChatService().answer(
        db=db,
        question=question,
        symbol=symbol,
        mode=mode,
        manual_option_snapshot_id=manual_option_snapshot_id,
        option_data_requested=option_data_requested,
    )
    return {"status": "OK", "response": response.to_dict()}
