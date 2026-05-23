"""Phase 27 — Today's Research Worklist API surface."""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.connection import get_db_session
from app.worklist.today_worklist_service import TodayWorklistService
from app.worklist.worklist_models import ResearchWorklistItem
from app.worklist.worklist_types import (
    ALL_STATUSES,
    STATUS_DISMISSED,
    STATUS_DONE,
    STATUS_OPEN,
)

router = APIRouter(prefix="/api/worklist", tags=["worklist"])


def _item_to_dict(item: ResearchWorklistItem) -> dict[str, Any]:
    return {
        "id": item.id,
        "worklist_date": item.worklist_date.isoformat() if item.worklist_date else None,
        "symbol": item.symbol,
        "worklist_type": item.worklist_type,
        "source": item.source,
        "priority": item.priority,
        "rank": item.rank,
        "title": item.title,
        "summary": item.summary,
        "context": item.context_json or {},
        "final_action_label": item.final_action_label,
        "lifecycle_state": item.lifecycle_state,
        "instrument_scope": item.instrument_scope,
        "status": item.status,
        "resolved_at": item.resolved_at.isoformat() if item.resolved_at else None,
        "resolution_notes": item.resolution_notes,
        "profile_name": item.profile_name,
        "profile_version": item.profile_version,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }


def _parse_date(value: str | None) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"invalid date '{value}'.") from exc


@router.post("/generate")
def generate_worklist(
    payload: dict[str, Any] = Body(default_factory=dict),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """Generate (or refresh) the worklist for a day from existing artifacts."""
    symbols = payload.get("symbols")
    if symbols is not None and not isinstance(symbols, list):
        raise HTTPException(status_code=400, detail="symbols must be a list.")
    worklist_date = _parse_date(payload.get("worklist_date"))
    result = TodayWorklistService().generate_worklist(
        db=db, worklist_date=worklist_date, symbols=symbols
    )
    return {"status": "OK", "result": result.to_dict()}


@router.get("")
def list_worklist(
    worklist_date: str | None = Query(default=None),
    status: str | None = Query(default=None),
    worklist_type: str | None = Query(default=None),
    symbol: str | None = Query(default=None),
    limit: int = Query(default=500, ge=1, le=1000),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    if status is not None and status.upper() not in ALL_STATUSES:
        raise HTTPException(status_code=400, detail=f"unknown status '{status}'.")
    parsed_date = _parse_date(worklist_date)
    items = TodayWorklistService().list_items(
        db=db,
        worklist_date=parsed_date,
        status=status,
        worklist_type=worklist_type,
        symbol=symbol,
        limit=limit,
    )
    return {
        "status": "OK",
        "count": len(items),
        "items": [_item_to_dict(i) for i in items],
    }


def _transition(
    db: Session, item_id: int, status: str, notes: str | None = None
) -> ResearchWorklistItem:
    item = TodayWorklistService().transition_status(
        db=db, item_id=item_id, new_status=status, notes=notes
    )
    if item is None:
        raise HTTPException(status_code=404, detail=f"worklist item {item_id} not found.")
    return item


@router.post("/items/{item_id}/done")
def mark_done(
    item_id: int,
    payload: dict[str, Any] = Body(default_factory=dict),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    notes = payload.get("notes")
    item = _transition(db, item_id, STATUS_DONE, notes)
    return {"status": "OK", "item": _item_to_dict(item)}


@router.post("/items/{item_id}/dismiss")
def mark_dismissed(
    item_id: int,
    payload: dict[str, Any] = Body(default_factory=dict),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    notes = payload.get("notes")
    item = _transition(db, item_id, STATUS_DISMISSED, notes)
    return {"status": "OK", "item": _item_to_dict(item)}


@router.post("/items/{item_id}/reopen")
def reopen(
    item_id: int,
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    item = _transition(db, item_id, STATUS_OPEN)
    return {"status": "OK", "item": _item_to_dict(item)}
