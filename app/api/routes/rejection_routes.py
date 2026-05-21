"""Phase 23 — Rejection intelligence API surface."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.connection import get_db_session
from app.rejection.rejection_models import RejectedCandidate, RejectionReason
from app.rejection.rejection_service import RejectionService

router = APIRouter(prefix="/api/rejections", tags=["rejections"])


def _candidate_to_dict(
    candidate: RejectedCandidate,
    reasons: list[RejectionReason],
) -> dict[str, Any]:
    return {
        "id": candidate.id,
        "symbol": candidate.symbol,
        "snapshot_date": candidate.snapshot_date.isoformat()
        if candidate.snapshot_date is not None
        else None,
        "rejection_category": candidate.rejection_category,
        "rejection_severity": candidate.rejection_severity,
        "final_action_label": candidate.final_action_label,
        "lifecycle_state": candidate.lifecycle_state,
        "is_rejected_but_interesting": bool(candidate.is_rejected_but_interesting),
        "interesting_reasons": candidate.interesting_reasons_json or [],
        "summary": candidate.summary,
        "profile_name": candidate.profile_name,
        "profile_version": candidate.profile_version,
        "created_at": candidate.created_at.isoformat() if candidate.created_at else None,
        "updated_at": candidate.updated_at.isoformat() if candidate.updated_at else None,
        "reasons": [
            {
                "id": r.id,
                "reason_label": r.reason_label,
                "reason_category": r.reason_category,
                "source_phase": r.source_phase,
                "explanation": r.explanation,
                "context": r.context_json or {},
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in reasons
        ],
    }


@router.get("/interesting")
def list_rejected_but_interesting(
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """Return rejected candidates that are flagged as worth watching.

    Defined before ``/{symbol}`` so the path ``/interesting`` is not
    swallowed by the dynamic path parameter.
    """
    rows = (
        db.query(RejectedCandidate)
        .filter(RejectedCandidate.is_rejected_but_interesting.is_(True))
        .order_by(
            RejectedCandidate.snapshot_date.desc(),
            RejectedCandidate.id.desc(),
        )
        .limit(limit)
        .all()
    )
    payloads: list[dict[str, Any]] = []
    for c in rows:
        reasons = (
            db.query(RejectionReason)
            .filter(RejectionReason.rejected_candidate_id == c.id)
            .order_by(RejectionReason.id.asc())
            .all()
        )
        payloads.append(_candidate_to_dict(c, reasons))
    return {"status": "OK", "count": len(payloads), "candidates": payloads}


@router.get("/{symbol}")
def get_rejection(
    symbol: str,
    manual_option_snapshot_id: int | None = Query(default=None),
    option_data_requested: bool = Query(default=False),
    persist: bool = Query(default=False),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """Run the Phase 23 rejection classifier for ``symbol``.

    ``persist=true`` writes the rejection envelope to
    ``rejected_candidates`` / ``rejection_reasons``. With ``persist=false``
    (the default) the route is idempotent and side-effect-free.
    """
    clean = (symbol or "").strip().upper()
    if not clean:
        raise HTTPException(status_code=400, detail="symbol is required.")

    try:
        evaluation = RejectionService().evaluate_symbol(
            db=db,
            symbol=clean,
            manual_option_snapshot_id=manual_option_snapshot_id,
            option_data_requested=option_data_requested,
            persist=persist,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return {"status": "OK", "evaluation": evaluation.to_dict()}


@router.get("")
def list_rejections(
    symbol: str | None = Query(default=None),
    category: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    query = db.query(RejectedCandidate)
    if symbol is not None:
        query = query.filter(RejectedCandidate.symbol == symbol.strip().upper())
    if category is not None:
        query = query.filter(RejectedCandidate.rejection_category == category.upper())

    rows = (
        query.order_by(
            RejectedCandidate.snapshot_date.desc(),
            RejectedCandidate.id.desc(),
        )
        .limit(limit)
        .all()
    )
    payloads: list[dict[str, Any]] = []
    for c in rows:
        reasons = (
            db.query(RejectionReason)
            .filter(RejectionReason.rejected_candidate_id == c.id)
            .order_by(RejectionReason.id.asc())
            .all()
        )
        payloads.append(_candidate_to_dict(c, reasons))
    return {"status": "OK", "count": len(payloads), "candidates": payloads}
