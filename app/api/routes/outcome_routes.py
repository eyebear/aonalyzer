"""Phases 39-40 — signal & rejection outcome tracking API surface."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy.orm import Session

from app.database.connection import get_db_session
from app.learning.rejection_outcome_models import RejectionOutcome
from app.learning.rejection_outcome_service import RejectionOutcomeService
from app.learning.signal_outcome_models import SignalOutcome
from app.learning.signal_outcome_service import SignalOutcomeService

router = APIRouter(prefix="/api/outcomes", tags=["outcomes"])


def _signal_to_dict(o: SignalOutcome) -> dict[str, Any]:
    return {
        "id": o.id,
        "symbol": o.symbol,
        "signal_date": o.signal_date.isoformat() if o.signal_date else None,
        "horizon_days": o.horizon_days,
        "final_action_label": o.final_action_label,
        "instrument_scope": o.instrument_scope,
        "direction": o.direction,
        "price_data_available": o.price_data_available,
        "stock_return_pct": o.stock_return_pct,
        "target_hit": o.target_hit,
        "stop_hit": o.stop_hit,
        "option_outcome_status": o.option_outcome_status,
        "option_return_pct": o.option_return_pct,
        "evaluated_at": o.evaluated_at.isoformat() if o.evaluated_at else None,
    }


def _rejection_to_dict(o: RejectionOutcome) -> dict[str, Any]:
    return {
        "id": o.id,
        "symbol": o.symbol,
        "snapshot_date": o.snapshot_date.isoformat() if o.snapshot_date else None,
        "horizon_days": o.horizon_days,
        "source_type": o.source_type,
        "category": o.category,
        "severity": o.severity,
        "price_data_available": o.price_data_available,
        "stock_return_pct": o.stock_return_pct,
        "would_stock_target_hit": o.would_stock_target_hit,
        "option_data_available": o.option_data_available,
        "would_option_have_worked": o.would_option_have_worked,
        "was_rejection_correct": o.was_rejection_correct,
        "is_too_strict": o.is_too_strict,
        "detail": o.detail,
    }


@router.post("/signals/run")
def run_signal_outcomes(
    payload: dict[str, Any] = Body(default_factory=dict),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    symbols = payload.get("symbols")
    result = SignalOutcomeService().run(db=db, symbols=symbols)
    return {"status": "OK", "result": result.to_dict()}


@router.get("/signals")
def list_signal_outcomes(
    symbol: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    rows = SignalOutcomeService().list_outcomes(db=db, symbol=symbol, limit=limit)
    return {"status": "OK", "count": len(rows), "outcomes": [_signal_to_dict(r) for r in rows]}


@router.post("/rejections/run")
def run_rejection_outcomes(
    payload: dict[str, Any] = Body(default_factory=dict),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    result = RejectionOutcomeService().run(db=db, horizon_days=payload.get("horizon_days"))
    return {"status": "OK", "result": result.to_dict()}


@router.get("/rejections")
def list_rejection_outcomes(
    symbol: str | None = Query(default=None),
    source_type: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    rows = RejectionOutcomeService().list_outcomes(
        db=db, symbol=symbol, source_type=source_type, limit=limit
    )
    return {"status": "OK", "count": len(rows), "outcomes": [_rejection_to_dict(r) for r in rows]}
