from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.ai_analysis.event_analysis_models import EventAnalysis
from app.ai_analysis.event_analysis_service import EventAnalysisService
from app.ai_analysis.option_text_analysis_service import OptionTextAnalysisService
from app.common.service_utils import ensure_tables
from app.database.connection import get_db_session

router = APIRouter(prefix="/api/ai-analysis", tags=["ai-analysis"])


def _event_analysis_to_dict(row: EventAnalysis) -> dict[str, Any]:
    return {
        "event_id": row.event_id,
        "symbol": row.symbol,
        "analysis_status": row.analysis_status,
        "is_fallback": row.is_fallback,
        "summary": row.summary,
        "sentiment": row.sentiment,
        "price_impact": row.price_impact,
        "confidence": row.confidence,
        "key_points": row.key_points_json or [],
        "risk_flags": row.risk_flags_json or [],
        "affected_symbols": row.affected_symbols_json or [],
        "provider_type": row.provider_type,
        "model": row.model,
        "prompt_version": row.prompt_version,
        "fallback_reason": row.fallback_reason,
    }


@router.post("/events/{event_id}")
def analyze_event(event_id: int, session: Session = Depends(get_db_session)) -> dict[str, Any]:
    service = EventAnalysisService()
    try:
        row = service.analyze_event(session, event_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"status": "OK", "analysis": _event_analysis_to_dict(row)}


@router.get("/events/{event_id}")
def get_event_analysis(event_id: int, session: Session = Depends(get_db_session)) -> dict[str, Any]:
    ensure_tables(session)
    row = (
        session.query(EventAnalysis)
        .filter(EventAnalysis.event_id == event_id)
        .one_or_none()
    )
    if row is None:
        return {"status": "OK", "event_id": event_id, "analysis": None}
    return {"status": "OK", "analysis": _event_analysis_to_dict(row)}


@router.post("/events/refresh-high-importance")
def refresh_high_importance(
    limit: int = Query(default=20, ge=1, le=200),
    session: Session = Depends(get_db_session),
) -> dict[str, Any]:
    service = EventAnalysisService()
    summary = service.analyze_high_importance(session, limit=limit)
    return {"status": "OK", **summary}


@router.post("/options/{snapshot_id}")
def analyze_option_text(
    snapshot_id: int,
    session: Session = Depends(get_db_session),
) -> dict[str, Any]:
    service = OptionTextAnalysisService()
    try:
        result = service.analyze_snapshot(session, snapshot_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"status": "OK", "snapshot_id": snapshot_id, "analysis": result.to_dict()}


@router.get("/options/{snapshot_id}")
def get_option_analysis(
    snapshot_id: int,
    session: Session = Depends(get_db_session),
) -> dict[str, Any]:
    service = OptionTextAnalysisService()
    stored = service.get_stored_analysis(session, snapshot_id)
    if stored is None:
        raise HTTPException(status_code=404, detail=f"Snapshot {snapshot_id} not found.")
    return {"status": "OK", **stored}
