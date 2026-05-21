"""Phase 25 — Opportunity lifecycle API surface."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.connection import get_db_session
from app.lifecycle.lifecycle_models import (
    OpportunityLifecycle,
    OpportunityStateTransition,
)
from app.lifecycle.lifecycle_service import LifecycleService
from app.lifecycle.lifecycle_states import (
    ALL_REVIEW_STATUSES,
    REVIEW_REVIEWED,
)
from app.lifecycle.lifecycle_update_job import LifecycleUpdateJob

router = APIRouter(prefix="/api/lifecycle", tags=["lifecycle"])


def _lifecycle_to_dict(row: OpportunityLifecycle) -> dict[str, Any]:
    return {
        "id": row.id,
        "symbol": row.symbol,
        "current_state": row.current_state,
        "previous_state": row.previous_state,
        "last_transition_at": row.last_transition_at.isoformat()
        if row.last_transition_at
        else None,
        "last_evaluated_at": row.last_evaluated_at.isoformat()
        if row.last_evaluated_at
        else None,
        "final_action_label": row.final_action_label,
        "user_review_status": row.user_review_status,
        "user_reviewed_at": row.user_reviewed_at.isoformat()
        if row.user_reviewed_at
        else None,
        "last_reactivation_at": row.last_reactivation_at.isoformat()
        if row.last_reactivation_at
        else None,
        "profile_name": row.profile_name,
        "profile_version": row.profile_version,
        "context": row.context_json or {},
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _transition_to_dict(row: OpportunityStateTransition) -> dict[str, Any]:
    return {
        "id": row.id,
        "symbol": row.symbol,
        "from_state": row.from_state,
        "to_state": row.to_state,
        "transition_reason_label": row.transition_reason_label,
        "transition_reason_summary": row.transition_reason_summary,
        "triggered_by": row.triggered_by,
        "source_phase": row.source_phase,
        "final_action_label": row.final_action_label,
        "context": row.context_json or {},
        "profile_name": row.profile_name,
        "profile_version": row.profile_version,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


# ----- Listing + history (defined before /{symbol}) ------------------------


@router.get("/history/{symbol}")
def get_history(
    symbol: str,
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    clean = (symbol or "").strip().upper()
    if not clean:
        raise HTTPException(status_code=400, detail="symbol is required.")
    rows = LifecycleService().get_history(db=db, symbol=clean, limit=limit)
    return {
        "status": "OK",
        "symbol": clean,
        "count": len(rows),
        "history": [_transition_to_dict(r) for r in rows],
    }


@router.post("/update")
def run_update_job(
    payload: dict[str, Any] = Body(default_factory=dict),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    symbols = payload.get("symbols")
    if symbols is not None and not isinstance(symbols, list):
        raise HTTPException(
            status_code=400, detail="symbols must be a list when provided."
        )
    option_data_requested = bool(payload.get("option_data_requested", False))
    result = LifecycleUpdateJob().run(
        db=db,
        symbols=symbols,
        option_data_requested=option_data_requested,
    )
    return {"status": "OK", "result": result.to_dict()}


@router.post("/reactivate")
def run_reactivation(
    payload: dict[str, Any] = Body(default_factory=dict),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    symbols = payload.get("symbols")
    if symbols is not None and not isinstance(symbols, list):
        raise HTTPException(
            status_code=400, detail="symbols must be a list when provided."
        )
    option_data_requested = bool(payload.get("option_data_requested", False))
    results = LifecycleService().detect_reactivations(
        db=db,
        symbols=symbols,
        option_data_requested=option_data_requested,
    )
    return {
        "status": "OK",
        "reactivations": [
            {
                "lifecycle_id": r.lifecycle.id,
                "symbol": r.lifecycle.symbol,
                "from_state": r.update.plan.from_state,
                "to_state": r.update.plan.to_state,
            }
            for r in results
        ],
    }


@router.get("")
def list_lifecycles(
    state: str | None = Query(default=None),
    review_status: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    rows = LifecycleService().list_active(db=db)
    if state is not None:
        rows = [r for r in rows if r.current_state == state.upper()]
    if review_status is not None:
        rows = [r for r in rows if r.user_review_status == review_status.upper()]
    rows = rows[:limit]
    return {
        "status": "OK",
        "count": len(rows),
        "lifecycles": [_lifecycle_to_dict(r) for r in rows],
    }


# ----- Per-symbol endpoints ------------------------------------------------


@router.get("/{symbol}")
def get_or_evaluate_lifecycle(
    symbol: str,
    manual_option_snapshot_id: int | None = Query(default=None),
    option_data_requested: bool = Query(default=False),
    evaluate: bool = Query(
        default=True,
        description=(
            "When true (default), re-runs the Phase 22 chain and updates the "
            "lifecycle row. When false, returns only the persisted state."
        ),
    ),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    clean = (symbol or "").strip().upper()
    if not clean:
        raise HTTPException(status_code=400, detail="symbol is required.")

    service = LifecycleService()
    if evaluate:
        try:
            evaluation = service.evaluate_symbol(
                db=db,
                symbol=clean,
                manual_option_snapshot_id=manual_option_snapshot_id,
                option_data_requested=option_data_requested,
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {
            "status": "OK",
            "lifecycle": _lifecycle_to_dict(evaluation.lifecycle),
            "update": evaluation.update.to_dict(),
        }

    row = service.get(db=db, symbol=clean)
    return {
        "status": "OK",
        "lifecycle": _lifecycle_to_dict(row) if row is not None else None,
    }


@router.post("/{symbol}/review")
def mark_review(
    symbol: str,
    payload: dict[str, Any] = Body(default_factory=dict),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    clean = (symbol or "").strip().upper()
    if not clean:
        raise HTTPException(status_code=400, detail="symbol is required.")
    review_status = str(
        payload.get("review_status", REVIEW_REVIEWED)
    ).upper()
    if review_status not in ALL_REVIEW_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"unknown review_status '{review_status}'. Allowed: "
                + ", ".join(sorted(ALL_REVIEW_STATUSES))
            ),
        )
    notes = payload.get("notes")
    if notes is not None and not isinstance(notes, str):
        raise HTTPException(status_code=400, detail="notes must be a string.")

    result = LifecycleService().mark_review(
        db=db, symbol=clean, review_status=review_status, notes=notes
    )
    if not result.get("updated"):
        raise HTTPException(
            status_code=404,
            detail=f"No lifecycle row exists for {clean}; evaluate it first.",
        )
    return {"status": "OK", "symbol": clean, "result": result}
