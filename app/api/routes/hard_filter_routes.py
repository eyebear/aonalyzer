"""Phase 20 — Hard Filter API surface."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.connection import get_db_session
from app.hard_filter.hard_filter_models import HardFilterResult
from app.hard_filter.hard_filter_service import HardFilterService
from app.options.manual_option_input_service import ManualOptionInputService

router = APIRouter(prefix="/api/hard-filters", tags=["hard-filters"])


@router.get("/{symbol}")
def get_hard_filter_decision(
    symbol: str,
    manual_option_snapshot_id: int | None = Query(default=None),
    persist: bool = Query(default=False),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """Run the Phase 20 hard filter gate for ``symbol``.

    * ``manual_option_snapshot_id`` (optional): when supplied, the gate uses
      the stored manual option snapshot to run the optional option-side
      filters. When omitted, option filters are SKIPPED and the stock
      decision still runs.
    * ``persist``: when True, writes the result to ``hard_filter_results``.
      Defaults to False to keep the GET idempotent in dashboards.
    """
    clean = (symbol or "").strip().upper()
    if not clean:
        raise HTTPException(status_code=400, detail="symbol is required.")

    option_snapshot = None
    if manual_option_snapshot_id is not None:
        option_snapshot = ManualOptionInputService().get_manual_snapshot_by_id(
            db=db, snapshot_id=manual_option_snapshot_id
        )
        if option_snapshot is None:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"Manual option snapshot {manual_option_snapshot_id} "
                    "was not found."
                ),
            )

    service = HardFilterService()
    evaluation = service.evaluate_symbol(
        db=db,
        symbol=clean,
        option_snapshot=option_snapshot,
        persist=persist,
    )

    return {
        "status": "OK",
        "decision": evaluation.decision.to_dict(),
        "record_id": (
            evaluation.record.id if evaluation.record is not None else None
        ),
    }


@router.get("")
def list_hard_filter_decisions(
    symbol: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """Return persisted hard-filter results for dashboards and decision trace."""
    query = db.query(HardFilterResult)
    if symbol is not None:
        query = query.filter(HardFilterResult.symbol == symbol.strip().upper())

    rows = (
        query.order_by(
            HardFilterResult.snapshot_date.desc(),
            HardFilterResult.id.desc(),
        )
        .limit(limit)
        .all()
    )

    return {
        "status": "OK",
        "count": len(rows),
        "results": [
            {
                "id": r.id,
                "symbol": r.symbol,
                "snapshot_date": r.snapshot_date.isoformat()
                if r.snapshot_date is not None
                else None,
                "overall_decision": r.overall_decision,
                "option_decision": r.option_decision,
                "stock_blocking_labels": r.stock_blocking_labels_json or [],
                "option_blocking_labels": r.option_blocking_labels_json or [],
                "warning_labels": r.warning_labels_json or [],
                "skipped_filters": r.skipped_filters_json or [],
                "reasons": r.reasons_json or [],
                "outcomes": r.outcomes_json or [],
                "profile_name": r.profile_name,
                "profile_version": r.profile_version,
                "stock_risk_reward": r.stock_risk_reward,
                "price_extension_atr": r.price_extension_atr,
                "price_extension_sma50_percent": r.price_extension_sma50_percent,
                "regime_label": r.regime_label,
                "earnings_risk_label": r.earnings_risk_label,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            }
            for r in rows
        ],
    }
