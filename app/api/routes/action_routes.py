"""Phase 22 — Action suggestion API surface."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.action.action_models import ActionSuggestion
from app.action.action_service import ActionSuggestionService
from app.database.connection import get_db_session

router = APIRouter(prefix="/api/action-suggestions", tags=["action-suggestions"])


@router.get("/{symbol}")
def get_action_suggestion(
    symbol: str,
    manual_option_snapshot_id: int | None = Query(default=None),
    option_data_requested: bool = Query(default=False),
    persist: bool = Query(default=False),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """Run the Phase 22 action layer for ``symbol``.

    Shape matches the Phase 22 outline: the ``package`` field carries all
    18+ documented entries (final_action_label, instrument_scope,
    lifecycle_state, ..., action_items).
    """
    clean = (symbol or "").strip().upper()
    if not clean:
        raise HTTPException(status_code=400, detail="symbol is required.")

    try:
        evaluation = ActionSuggestionService().evaluate_symbol(
            db=db,
            symbol=clean,
            manual_option_snapshot_id=manual_option_snapshot_id,
            option_data_requested=option_data_requested,
            persist=persist,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return {
        "status": "OK",
        "package": evaluation.package.to_dict(),
        "record_id": evaluation.record.id if evaluation.record is not None else None,
    }


@router.get("")
def list_action_suggestions(
    symbol: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    query = db.query(ActionSuggestion)
    if symbol is not None:
        query = query.filter(ActionSuggestion.symbol == symbol.strip().upper())

    rows = (
        query.order_by(
            ActionSuggestion.snapshot_date.desc(),
            ActionSuggestion.id.desc(),
        )
        .limit(limit)
        .all()
    )

    return {
        "status": "OK",
        "count": len(rows),
        "suggestions": [
            {
                "id": r.id,
                "symbol": r.symbol,
                "snapshot_date": r.snapshot_date.isoformat()
                if r.snapshot_date is not None
                else None,
                "final_action_label": r.final_action_label,
                "instrument_scope": r.instrument_scope,
                "lifecycle_state": r.lifecycle_state,
                "option_expression_status": r.option_expression_status,
                "manual_option_input_needed": bool(r.manual_option_input_needed),
                "priority_score": r.priority_score,
                "confidence_score": r.confidence_score,
                "suggested_action_summary": r.suggested_action_summary,
                "entry_condition": r.entry_condition_json or {},
                "option_contract_criteria": r.option_contract_criteria_json,
                "invalidation_condition": r.invalidation_condition_json or {},
                "upgrade_condition": r.upgrade_condition_json or {},
                "downgrade_condition": r.downgrade_condition_json or {},
                "watch_condition": r.watch_condition_json or {},
                "next_review_trigger": r.next_review_trigger_json or {},
                "decision_trace": r.decision_trace_json or [],
                "version_stamp": r.version_stamp_json or {},
                "action_items": r.action_items_json or [],
                "profile_name": r.profile_name,
                "profile_version": r.profile_version,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            }
            for r in rows
        ],
    }
