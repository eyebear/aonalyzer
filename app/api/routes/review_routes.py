"""Phase 26 — Review queue API surface."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.connection import get_db_session
from app.review.review_models import ReviewQueueItem, ReviewTrigger
from app.review.review_service import ReviewService
from app.review.review_trigger_types import (
    ALL_QUEUE_STATUSES,
    QUEUE_STATUS_DISMISSED,
    QUEUE_STATUS_IN_REVIEW,
    QUEUE_STATUS_PENDING,
    QUEUE_STATUS_RESOLVED,
)
from app.review.scheduled_review_trigger_job import ScheduledReviewTriggerJob

router = APIRouter(prefix="/api/review-queue", tags=["review-queue"])


def _queue_item_to_dict(item: ReviewQueueItem) -> dict[str, Any]:
    return {
        "id": item.id,
        "symbol": item.symbol,
        "trigger_type": item.trigger_type,
        "status": item.status,
        "priority": item.priority,
        "summary": item.summary,
        "review_reason_label": item.review_reason_label,
        "context": item.context_json or {},
        "lifecycle_state": item.lifecycle_state,
        "due_at": item.due_at.isoformat() if item.due_at else None,
        "resolved_at": item.resolved_at.isoformat() if item.resolved_at else None,
        "resolution_notes": item.resolution_notes,
        "source_phase": item.source_phase,
        "profile_name": item.profile_name,
        "profile_version": item.profile_version,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }


def _trigger_to_dict(trigger: ReviewTrigger) -> dict[str, Any]:
    return {
        "id": trigger.id,
        "symbol": trigger.symbol,
        "trigger_type": trigger.trigger_type,
        "is_active": bool(trigger.is_active),
        "condition": trigger.condition_json or {},
        "lifecycle_state": trigger.lifecycle_state,
        "last_evaluated_at": trigger.last_evaluated_at.isoformat()
        if trigger.last_evaluated_at
        else None,
        "last_fired_at": trigger.last_fired_at.isoformat()
        if trigger.last_fired_at
        else None,
        "fire_count": trigger.fire_count,
        "profile_name": trigger.profile_name,
        "profile_version": trigger.profile_version,
        "created_at": trigger.created_at.isoformat() if trigger.created_at else None,
        "updated_at": trigger.updated_at.isoformat() if trigger.updated_at else None,
    }


# ----- Static paths first --------------------------------------------------


@router.post("/run-triggers")
def run_triggers(
    payload: dict[str, Any] = Body(default_factory=dict),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """Arm + evaluate review triggers for the listed symbols (or every
    tracked symbol when none is given)."""
    symbols = payload.get("symbols")
    if symbols is not None and not isinstance(symbols, list):
        raise HTTPException(
            status_code=400, detail="symbols must be a list when provided."
        )
    job = ScheduledReviewTriggerJob()
    result = job.run(db=db, symbols=symbols)
    return {"status": "OK", "result": result.to_dict()}


@router.get("/triggers")
def list_triggers(
    symbol: str | None = Query(default=None),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    triggers = ReviewService().list_armed_triggers(db=db, symbol=symbol)
    return {
        "status": "OK",
        "count": len(triggers),
        "triggers": [_trigger_to_dict(t) for t in triggers],
    }


@router.get("/{symbol}")
def list_queue_for_symbol(
    symbol: str,
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    clean = (symbol or "").strip().upper()
    if not clean:
        raise HTTPException(status_code=400, detail="symbol is required.")
    if status is not None and status.upper() not in ALL_QUEUE_STATUSES:
        raise HTTPException(
            status_code=400, detail=f"unknown status '{status}'."
        )
    items = ReviewService().list_queue(
        db=db, symbol=clean, status=status, limit=limit
    )
    return {
        "status": "OK",
        "count": len(items),
        "items": [_queue_item_to_dict(i) for i in items],
    }


@router.get("")
def list_queue(
    status: str | None = Query(default=None),
    symbol: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    if status is not None and status.upper() not in ALL_QUEUE_STATUSES:
        raise HTTPException(
            status_code=400, detail=f"unknown status '{status}'."
        )
    items = ReviewService().list_queue(
        db=db, symbol=symbol, status=status, limit=limit
    )
    return {
        "status": "OK",
        "count": len(items),
        "items": [_queue_item_to_dict(i) for i in items],
    }


# ----- Per-item mutations --------------------------------------------------


def _transition(
    db: Session, queue_id: int, status: str, notes: str | None = None
) -> ReviewQueueItem:
    item = ReviewService().transition_status(
        db=db, queue_id=queue_id, new_status=status, notes=notes
    )
    if item is None:
        raise HTTPException(
            status_code=404, detail=f"queue item {queue_id} not found."
        )
    return item


@router.post("/items/{queue_id}/resolve")
def resolve_item(
    queue_id: int,
    payload: dict[str, Any] = Body(default_factory=dict),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    notes = payload.get("notes")
    if notes is not None and not isinstance(notes, str):
        raise HTTPException(status_code=400, detail="notes must be a string.")
    item = _transition(db, queue_id, QUEUE_STATUS_RESOLVED, notes)
    return {"status": "OK", "item": _queue_item_to_dict(item)}


@router.post("/items/{queue_id}/dismiss")
def dismiss_item(
    queue_id: int,
    payload: dict[str, Any] = Body(default_factory=dict),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    notes = payload.get("notes")
    if notes is not None and not isinstance(notes, str):
        raise HTTPException(status_code=400, detail="notes must be a string.")
    item = _transition(db, queue_id, QUEUE_STATUS_DISMISSED, notes)
    return {"status": "OK", "item": _queue_item_to_dict(item)}


@router.post("/items/{queue_id}/in-review")
def mark_in_review(
    queue_id: int,
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    item = _transition(db, queue_id, QUEUE_STATUS_IN_REVIEW)
    return {"status": "OK", "item": _queue_item_to_dict(item)}


@router.post("/items/{queue_id}/reopen")
def reopen_item(
    queue_id: int,
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    item = _transition(db, queue_id, QUEUE_STATUS_PENDING)
    return {"status": "OK", "item": _queue_item_to_dict(item)}
