"""Phase 49 — end-to-end orchestration API surface."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from app.agent.full_pipeline import FullPipeline
from app.database.connection import get_db_session

router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])


@router.post("/run")
def run_pipeline(
    payload: dict[str, Any] = Body(default_factory=dict),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    symbols = payload.get("symbols")
    if symbols is not None and not isinstance(symbols, list):
        raise HTTPException(status_code=400, detail="symbols must be a list.")
    result = FullPipeline().run(db=db, symbols=symbols)
    return {"status": "OK", "result": result.to_dict()}
