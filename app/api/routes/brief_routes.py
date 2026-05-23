"""Phase 28, step 28.15 — One-Page Ticker Brief API surface."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.brief.ticker_brief_models import TickerBrief
from app.brief.ticker_brief_service import TickerBriefService
from app.database.connection import get_db_session

router = APIRouter(prefix="/api/ticker-brief", tags=["ticker-brief"])


def _record_to_dict(row: TickerBrief) -> dict[str, Any]:
    return {
        "id": row.id,
        "symbol": row.symbol,
        "snapshot_date": row.snapshot_date.isoformat() if row.snapshot_date else None,
        "final_action_label": row.final_action_label,
        "instrument_scope": row.instrument_scope,
        "lifecycle_state": row.lifecycle_state,
        "option_expression_status": row.option_expression_status,
        "priority_score": row.priority_score,
        "confidence_score": row.confidence_score,
        "sections": row.sections_json or [],
        "version_stamp": row.version_stamp_json or {},
        "profile_name": row.profile_name,
        "profile_version": row.profile_version,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


@router.get("/{symbol}")
def get_ticker_brief(
    symbol: str,
    manual_option_snapshot_id: int | None = Query(default=None),
    option_data_requested: bool = Query(default=False),
    persist: bool = Query(default=False),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    try:
        evaluation = TickerBriefService().build_brief(
            db=db,
            symbol=symbol,
            manual_option_snapshot_id=manual_option_snapshot_id,
            option_data_requested=option_data_requested,
            persist=persist,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "status": "OK",
        "brief": evaluation.brief.to_dict(),
        "record_id": evaluation.record.id if evaluation.record is not None else None,
    }


@router.get("")
def list_ticker_briefs(
    symbol: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    rows = TickerBriefService().list_briefs(db=db, symbol=symbol, limit=limit)
    return {
        "status": "OK",
        "count": len(rows),
        "briefs": [_record_to_dict(r) for r in rows],
    }
