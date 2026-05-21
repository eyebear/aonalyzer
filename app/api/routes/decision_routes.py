"""Phase 21 — Decision Intelligence API surface."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.connection import get_db_session
from app.decision.decision_models import DecisionSnapshot
from app.decision.decision_service import DecisionService

router = APIRouter(prefix="/api/decisions", tags=["decisions"])


@router.get("/{symbol}")
def get_decision(
    symbol: str,
    manual_option_snapshot_id: int | None = Query(default=None),
    option_data_requested: bool = Query(default=False),
    persist: bool = Query(default=False),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """Run the Phase 21 decision engine for ``symbol``.

    * ``manual_option_snapshot_id``: when supplied, the option side of the
      Phase 20 hard filter runs against the stored manual option snapshot.
    * ``option_data_requested``: when ``True`` and no option data is
      available, the final label switches to ``OPTION_DATA_NOT_AVAILABLE``
      instead of ``READY_TO_RESEARCH_STOCK_ONLY``.
    * ``persist``: when ``True`` the snapshot is upserted into
      ``decision_snapshots``. Defaults to ``False`` so GETs are idempotent.
    """
    clean = (symbol or "").strip().upper()
    if not clean:
        raise HTTPException(status_code=400, detail="symbol is required.")

    try:
        evaluation = DecisionService().evaluate_symbol(
            db=db,
            symbol=clean,
            manual_option_snapshot_id=manual_option_snapshot_id,
            option_data_requested=option_data_requested,
            persist=persist,
        )
    except ValueError as exc:
        # Unknown option snapshot id raises ValueError from the service.
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return {
        "status": "OK",
        "decision": evaluation.decision.to_dict(),
        "record_id": evaluation.record.id if evaluation.record is not None else None,
    }


@router.get("")
def list_decisions(
    symbol: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """Return persisted decision snapshots for dashboards and audit."""
    query = db.query(DecisionSnapshot)
    if symbol is not None:
        query = query.filter(DecisionSnapshot.symbol == symbol.strip().upper())

    rows = (
        query.order_by(
            DecisionSnapshot.snapshot_date.desc(),
            DecisionSnapshot.id.desc(),
        )
        .limit(limit)
        .all()
    )

    return {
        "status": "OK",
        "count": len(rows),
        "decisions": [
            {
                "id": r.id,
                "symbol": r.symbol,
                "snapshot_date": r.snapshot_date.isoformat()
                if r.snapshot_date is not None
                else None,
                "final_label": r.final_label,
                "rationale": r.rationale,
                "stock_thesis_label": r.stock_thesis_label,
                "option_expression_label": r.option_expression_label,
                "instrument_scope": r.instrument_scope,
                "event_risk_level": r.event_risk_level,
                "memory_risk_level": r.memory_risk_level,
                "priority_score": r.priority_score,
                "confidence_score": r.confidence_score,
                "checklist": r.checklist_json or [],
                "trace": r.trace_json or [],
                "version_stamp": r.version_stamp_json or {},
                "profile_name": r.profile_name,
                "profile_version": r.profile_version,
                "option_data_requested": (r.option_data_requested == "TRUE"),
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            }
            for r in rows
        ],
    }
