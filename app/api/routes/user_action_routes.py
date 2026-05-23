"""Phase 38 — user action / override tracking API surface."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.connection import get_db_session
from app.user_actions.user_action_models import UserAction, UserOverride
from app.user_actions.user_action_service import UserActionService

router = APIRouter(prefix="/api/user-actions", tags=["user-actions"])


def _action_to_dict(a: UserAction) -> dict[str, Any]:
    return {
        "id": a.id,
        "symbol": a.symbol,
        "action_type": a.action_type,
        "action_date": a.action_date.isoformat() if a.action_date else None,
        "system_suggestion_label": a.system_suggestion_label,
        "system_instrument_scope": a.system_instrument_scope,
        "option_data_availability": a.option_data_availability,
        "manual_option_snapshot_id": a.manual_option_snapshot_id,
        "notes": a.notes,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


def _override_to_dict(o: UserOverride) -> dict[str, Any]:
    return {
        "id": o.id,
        "symbol": o.symbol,
        "override_type": o.override_type,
        "system_suggestion_label": o.system_suggestion_label,
        "user_action_type": o.user_action_type,
        "signal_date": o.signal_date.isoformat() if o.signal_date else None,
        "detected_at": o.detected_at.isoformat() if o.detected_at else None,
    }


@router.post("")
def record_action(
    payload: dict[str, Any] = Body(default_factory=dict),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    symbol = payload.get("symbol")
    action_type = payload.get("action_type")
    if not symbol or not action_type:
        raise HTTPException(status_code=400, detail="symbol and action_type are required.")
    try:
        result = UserActionService().record_action(
            db=db,
            symbol=symbol,
            action_type=action_type,
            system_suggestion_label=payload.get("system_suggestion_label"),
            system_instrument_scope=payload.get("system_instrument_scope"),
            manual_option_snapshot_id=payload.get("manual_option_snapshot_id"),
            option_data_available=payload.get("option_data_available"),
            notes=payload.get("notes"),
            context=payload.get("context"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "OK", "result": result.to_dict()}


@router.get("")
def list_actions(
    symbol: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    actions = UserActionService().list_actions(db=db, symbol=symbol, limit=limit)
    return {"status": "OK", "count": len(actions), "actions": [_action_to_dict(a) for a in actions]}


@router.get("/overrides")
def list_overrides(
    symbol: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    overrides = UserActionService().list_overrides(db=db, symbol=symbol, limit=limit)
    return {
        "status": "OK",
        "count": len(overrides),
        "overrides": [_override_to_dict(o) for o in overrides],
    }


@router.post("/track-outcomes")
def track_outcomes(
    payload: dict[str, Any] = Body(default_factory=dict),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    horizon = payload.get("horizon_days")
    result = UserActionService().track_override_outcomes(db=db, horizon_days=horizon)
    return {"status": "OK", "result": result}


@router.get("/decision-quality")
def decision_quality(db: Session = Depends(get_db_session)) -> dict[str, Any]:
    return {"status": "OK", "summary": UserActionService().analyze_decision_quality(db=db)}
