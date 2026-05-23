from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.common.service_utils import ensure_tables
from app.database.connection import get_db_session
from app.database.models import Event
from app.event_normalizer.event_labels import (
    KNOWN_EVENT_TYPES,
    KNOWN_IMPORTANCE_LEVELS,
)
from app.event_normalizer.freshness import EventFreshnessChecker

router = APIRouter(prefix="/api/events", tags=["events"])


def _ensure_event_table(session: Session) -> None:
    # Test/dev fallback only — no-op on PostgreSQL (schema owned by Alembic).
    ensure_tables(session)


def _event_to_dict(event: Event, freshness_checker: EventFreshnessChecker) -> dict[str, Any]:
    verdict = freshness_checker.check(event_time=event.event_time)

    return {
        "id": event.id,
        "event_type": event.event_type,
        "importance_level": event.importance_level,
        "source": event.source,
        "source_url": event.source_url,
        "source_title": event.source_title,
        "symbol": event.symbol,
        "market": event.market,
        "headline": event.headline,
        "raw_summary": event.raw_summary,
        "event_time": event.event_time.isoformat() if event.event_time else None,
        "detected_time": event.detected_time.isoformat() if event.detected_time else None,
        "content_hash": event.content_hash,
        "event_metadata": event.event_metadata_json or {},
        "is_reviewed": event.is_reviewed,
        "freshness": verdict.to_dict(),
    }


def _validate_filters(
    event_type: str | None,
    importance_level: str | None,
) -> None:
    if event_type is not None and event_type.upper() not in KNOWN_EVENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown event_type '{event_type}'.",
        )

    if importance_level is not None and importance_level.upper() not in KNOWN_IMPORTANCE_LEVELS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown importance_level '{importance_level}'.",
        )


def _apply_filters(
    query: Any,
    symbol: str | None,
    event_type: str | None,
    importance_level: str | None,
    source: str | None,
    since: datetime | None,
) -> Any:
    if symbol is not None:
        query = query.filter(Event.symbol == symbol.upper())

    if event_type is not None:
        query = query.filter(Event.event_type == event_type.upper())

    if importance_level is not None:
        query = query.filter(Event.importance_level == importance_level.upper())

    if source is not None:
        query = query.filter(Event.source == source)

    if since is not None:
        normalized_since = (
            since if since.tzinfo is not None else since.replace(tzinfo=timezone.utc)
        )
        query = query.filter(Event.detected_time >= normalized_since)

    return query


@router.get("")
def list_events(
    symbol: str | None = None,
    event_type: str | None = None,
    importance_level: str | None = None,
    source: str | None = None,
    since: datetime | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(get_db_session),
) -> dict[str, Any]:
    _ensure_event_table(session)
    _validate_filters(event_type=event_type, importance_level=importance_level)

    freshness_checker = EventFreshnessChecker()

    query = session.query(Event)
    query = _apply_filters(
        query=query,
        symbol=symbol,
        event_type=event_type,
        importance_level=importance_level,
        source=source,
        since=since,
    )

    events = (
        query.order_by(Event.detected_time.desc(), Event.id.desc())
        .limit(limit)
        .all()
    )

    return {
        "status": "OK",
        "count": len(events),
        "events": [_event_to_dict(event, freshness_checker) for event in events],
    }


@router.get("/recent")
def list_recent_events(
    hours: int = Query(default=24, ge=1, le=168),
    symbol: str | None = None,
    event_type: str | None = None,
    importance_level: str | None = None,
    source: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(get_db_session),
) -> dict[str, Any]:
    _ensure_event_table(session)
    _validate_filters(event_type=event_type, importance_level=importance_level)

    freshness_checker = EventFreshnessChecker(fresh_window_hours=hours)
    since = datetime.now(timezone.utc) - timedelta(hours=hours)

    query = session.query(Event)
    query = _apply_filters(
        query=query,
        symbol=symbol,
        event_type=event_type,
        importance_level=importance_level,
        source=source,
        since=since,
    )

    events = (
        query.order_by(Event.detected_time.desc(), Event.id.desc())
        .limit(limit)
        .all()
    )

    return {
        "status": "OK",
        "window_hours": hours,
        "since": since.isoformat(),
        "count": len(events),
        "events": [_event_to_dict(event, freshness_checker) for event in events],
    }


@router.post("/{event_id}/reviewed")
def set_event_reviewed(
    event_id: int,
    payload: dict[str, Any] = Body(default_factory=dict),
    session: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """Phase 36.10 — persist the user's reviewed flag for an event."""
    _ensure_event_table(session)

    event = session.query(Event).filter(Event.id == event_id).one_or_none()
    if event is None:
        raise HTTPException(status_code=404, detail=f"Event {event_id} not found.")

    reviewed = payload.get("reviewed", True)
    if not isinstance(reviewed, bool):
        raise HTTPException(status_code=400, detail="reviewed must be a boolean.")

    event.is_reviewed = reviewed
    session.commit()
    session.refresh(event)

    freshness_checker = EventFreshnessChecker()
    return {"status": "OK", "event": _event_to_dict(event, freshness_checker)}


@router.get("/{event_id}")
def get_event(
    event_id: int,
    session: Session = Depends(get_db_session),
) -> dict[str, Any]:
    _ensure_event_table(session)

    event = session.query(Event).filter(Event.id == event_id).one_or_none()

    if event is None:
        raise HTTPException(status_code=404, detail=f"Event {event_id} not found.")

    freshness_checker = EventFreshnessChecker()
    return {
        "status": "OK",
        "event": _event_to_dict(event, freshness_checker),
    }
