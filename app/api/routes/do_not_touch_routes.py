"""Phase 24 — Do-Not-Touch API surface."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.connection import get_db_session
from app.risk_control.do_not_touch_categories import (
    SEVERITY_HARD_FREEZE,
    SEVERITY_SOFT_FREEZE,
)
from app.risk_control.do_not_touch_models import DoNotTouchHistory, DoNotTouchItem
from app.risk_control.do_not_touch_service import DoNotTouchService
from app.risk_control.freeze_expiration_monitor import FreezeExpirationMonitor

router = APIRouter(prefix="/api/do-not-touch", tags=["do-not-touch"])


def _item_to_dict(item: DoNotTouchItem) -> dict[str, Any]:
    return {
        "id": item.id,
        "symbol": item.symbol,
        "freeze_category": item.freeze_category,
        "freeze_severity": item.freeze_severity,
        "frozen_at": item.frozen_at.isoformat() if item.frozen_at else None,
        "expires_at": item.expires_at.isoformat() if item.expires_at else None,
        "release_kind": item.release_kind,
        "release_condition_label": item.release_condition_label,
        "release_condition_description": item.release_condition_description,
        "reason_summary": item.reason_summary,
        "source_phase": item.source_phase,
        "triggered_by": item.triggered_by,
        "is_active": bool(item.is_active),
        "context": item.context_json or {},
        "profile_name": item.profile_name,
        "profile_version": item.profile_version,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }


def _history_row_to_dict(row: DoNotTouchHistory) -> dict[str, Any]:
    return {
        "id": row.id,
        "symbol": row.symbol,
        "event_type": row.event_type,
        "freeze_category": row.freeze_category,
        "freeze_severity": row.freeze_severity,
        "frozen_at": row.frozen_at.isoformat() if row.frozen_at else None,
        "expires_at": row.expires_at.isoformat() if row.expires_at else None,
        "released_at": row.released_at.isoformat() if row.released_at else None,
        "release_reason": row.release_reason,
        "reason_summary": row.reason_summary,
        "triggered_by": row.triggered_by,
        "source_phase": row.source_phase,
        "context": row.context_json or {},
        "profile_name": row.profile_name,
        "profile_version": row.profile_version,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


# ----- Listing / lookup (paths before the dynamic /{symbol}) ---------------


@router.post("/sweep-expired")
def sweep_expired(
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """Release any freezes whose ``expires_at`` is in the past."""
    monitor = FreezeExpirationMonitor()
    result = monitor.sweep_expired(db=db)
    return {"status": "OK", "result": result.to_dict()}


@router.get("/history/{symbol}")
def get_history(
    symbol: str,
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    clean = (symbol or "").strip().upper()
    if not clean:
        raise HTTPException(status_code=400, detail="symbol is required.")
    rows = (
        db.query(DoNotTouchHistory)
        .filter(DoNotTouchHistory.symbol == clean)
        .order_by(DoNotTouchHistory.created_at.desc(), DoNotTouchHistory.id.desc())
        .limit(limit)
        .all()
    )
    return {
        "status": "OK",
        "symbol": clean,
        "count": len(rows),
        "history": [_history_row_to_dict(r) for r in rows],
    }


@router.get("")
def list_active_freezes(
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    service = DoNotTouchService()
    items = service.list_active(db=db)[:limit]
    return {
        "status": "OK",
        "count": len(items),
        "items": [_item_to_dict(item) for item in items],
    }


# ----- Per-symbol evaluation + manual freeze/release -----------------------


@router.get("/{symbol}")
def get_or_evaluate_freeze(
    symbol: str,
    manual_option_snapshot_id: int | None = Query(default=None),
    option_data_requested: bool = Query(default=False),
    persist: bool = Query(default=False),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """Return the active freeze (if any) and run the classifier.

    ``persist=true`` applies any newly classified freeze to
    ``do_not_touch_items``. With ``persist=false`` the response is a
    dry-run with the explanation included.
    """
    clean = (symbol or "").strip().upper()
    if not clean:
        raise HTTPException(status_code=400, detail="symbol is required.")

    service = DoNotTouchService()
    try:
        evaluation = service.evaluate_symbol(
            db=db,
            symbol=clean,
            manual_option_snapshot_id=manual_option_snapshot_id,
            option_data_requested=option_data_requested,
            persist=persist,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    active = service.get_active(db=db, symbol=clean)
    return {
        "status": "OK",
        "symbol": clean,
        "active_freeze": _item_to_dict(active) if active is not None else None,
        "evaluation": evaluation.to_dict(),
    }


@router.post("/{symbol}/freeze")
def manual_freeze(
    symbol: str,
    payload: dict[str, Any] = Body(default_factory=dict),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    clean = (symbol or "").strip().upper()
    if not clean:
        raise HTTPException(status_code=400, detail="symbol is required.")

    reason = str(payload.get("reason") or "Manual freeze applied by user.")
    severity = str(payload.get("severity") or SEVERITY_HARD_FREEZE).upper()
    if severity not in {SEVERITY_HARD_FREEZE, SEVERITY_SOFT_FREEZE}:
        raise HTTPException(
            status_code=400, detail=f"unknown severity '{severity}'."
        )
    expires_at_iso = payload.get("expires_at")
    expires_at: datetime | None = None
    if expires_at_iso:
        try:
            expires_at = datetime.fromisoformat(expires_at_iso)
        except ValueError as exc:
            raise HTTPException(
                status_code=400, detail="expires_at must be ISO-8601."
            ) from exc

    service = DoNotTouchService()
    evaluation = service.manual_freeze(
        db=db,
        symbol=clean,
        reason=reason,
        severity=severity,
        expires_at=expires_at,
    )
    active = service.get_active(db=db, symbol=clean)
    return {
        "status": "OK",
        "symbol": clean,
        "active_freeze": _item_to_dict(active) if active is not None else None,
        "evaluation": evaluation.to_dict(),
    }


@router.post("/{symbol}/release")
def manual_release(
    symbol: str,
    payload: dict[str, Any] = Body(default_factory=dict),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    clean = (symbol or "").strip().upper()
    if not clean:
        raise HTTPException(status_code=400, detail="symbol is required.")
    reason = str(payload.get("reason") or "Manual release by user.")
    service = DoNotTouchService()
    operation = service.manual_release(db=db, symbol=clean, reason=reason)
    return {
        "status": "OK",
        "symbol": clean,
        "operation": operation.to_dict(),
    }
