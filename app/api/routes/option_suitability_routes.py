from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.common.service_utils import ensure_tables
from app.database.connection import get_db_session
from app.options.option_candidate_models import OptionCandidate
from app.options.option_suitability_service import OptionSuitabilityService

router = APIRouter(prefix="/api/option-suitability", tags=["option-suitability"])


def _ensure_tables(session: Session) -> None:
    ensure_tables(session)


def _candidate_to_dict(candidate: OptionCandidate) -> dict[str, Any]:
    return {
        "id": candidate.id,
        "symbol": candidate.symbol,
        "snapshot_date": candidate.snapshot_date.isoformat()
        if candidate.snapshot_date is not None
        else None,
        "manual_option_snapshot_id": candidate.manual_option_snapshot_id,
        "option_type": candidate.option_type,
        "strike": candidate.strike,
        "expiration_date": candidate.expiration_date.isoformat()
        if candidate.expiration_date is not None
        else None,
        "dte": candidate.dte,
        "premium": candidate.premium,
        "contract_cost": candidate.contract_cost,
        "bid": candidate.bid,
        "ask": candidate.ask,
        "spread_percent": candidate.spread_percent,
        "open_interest": candidate.open_interest,
        "volume": candidate.volume,
        "implied_volatility": candidate.implied_volatility,
        "iv_percent": candidate.iv_percent,
        "iv_state": candidate.iv_state,
        "breakeven": candidate.breakeven,
        "breakeven_distance_percent": candidate.breakeven_distance_percent,
        "target_price": candidate.target_price,
        "target_margin_percent": candidate.target_margin_percent,
        "liquidity_score": candidate.liquidity_score,
        "suitability_label": candidate.suitability_label,
        "is_suitable": candidate.is_suitable,
        "data_sufficiency_status": candidate.data_sufficiency_status,
        "rejection_labels": candidate.rejection_labels_json or [],
        "warning_labels": candidate.warning_labels_json or [],
        "outcomes": candidate.outcomes_json or [],
        "earnings_risk": candidate.earnings_risk_json,
        "reasons": candidate.reasons_json or [],
        "created_at": candidate.created_at.isoformat() if candidate.created_at else None,
        "updated_at": candidate.updated_at.isoformat() if candidate.updated_at else None,
    }


@router.post("/snapshots/{snapshot_id}/evaluate")
def evaluate_snapshot(
    snapshot_id: int,
    option_input_requested: bool = False,
    session: Session = Depends(get_db_session),
) -> dict[str, Any]:
    service = OptionSuitabilityService()
    try:
        candidate = service.evaluate_snapshot(
            session, snapshot_id, option_input_requested=option_input_requested
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return {"status": "OK", "candidate": _candidate_to_dict(candidate)}


@router.get("/status")
def get_no_option_status(
    symbol: str | None = None,
    option_input_requested: bool = False,
    session: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """No-option fallback: confirms missing option data is non-blocking."""
    service = OptionSuitabilityService()
    evaluation = service.evaluate_no_option(
        session, symbol, option_input_requested=option_input_requested
    )
    return {"status": "OK", **evaluation.to_dict()}


@router.get("/candidates")
def list_candidates(
    symbol: str | None = None,
    suitability_label: str | None = None,
    since: date | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(get_db_session),
) -> dict[str, Any]:
    _ensure_tables(session)

    query = session.query(OptionCandidate)
    if symbol is not None:
        query = query.filter(OptionCandidate.symbol == symbol.upper())
    if suitability_label is not None:
        query = query.filter(OptionCandidate.suitability_label == suitability_label.upper())
    if since is not None:
        query = query.filter(OptionCandidate.snapshot_date >= since)

    candidates = (
        query.order_by(OptionCandidate.snapshot_date.desc(), OptionCandidate.id.desc())
        .limit(limit)
        .all()
    )

    return {
        "status": "OK",
        "count": len(candidates),
        "candidates": [_candidate_to_dict(c) for c in candidates],
    }


@router.get("/candidates/latest")
def get_latest_candidate(
    symbol: str,
    session: Session = Depends(get_db_session),
) -> dict[str, Any]:
    _ensure_tables(session)

    clean_symbol = symbol.strip().upper()
    if not clean_symbol:
        raise HTTPException(status_code=400, detail="symbol is required.")

    candidate = (
        session.query(OptionCandidate)
        .filter(OptionCandidate.symbol == clean_symbol)
        .order_by(OptionCandidate.snapshot_date.desc(), OptionCandidate.id.desc())
        .first()
    )

    if candidate is None:
        return {
            "status": "OK",
            "symbol": clean_symbol,
            "candidate": None,
            "suitability_label": "OPTION_DATA_NOT_AVAILABLE",
            "reason": "No option candidate has been evaluated for this symbol yet.",
        }

    return {
        "status": "OK",
        "symbol": clean_symbol,
        "suitability_label": candidate.suitability_label,
        "candidate": _candidate_to_dict(candidate),
    }
