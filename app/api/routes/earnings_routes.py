from __future__ import annotations

from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.base import Base
from app.database.connection import get_db_session
from app.earnings.earnings_models import EarningsEvent, EarningsRiskSnapshot

router = APIRouter(prefix="/api/earnings", tags=["earnings"])


def _ensure_tables(session: Session) -> None:
    Base.metadata.create_all(bind=session.get_bind())


def _event_to_dict(event: EarningsEvent) -> dict[str, Any]:
    return {
        "id": event.id,
        "symbol": event.symbol,
        "earnings_datetime_utc": event.earnings_datetime_utc.isoformat()
        if event.earnings_datetime_utc is not None
        else None,
        "time_of_day": event.time_of_day,
        "confirmed": event.confirmed,
        "source": event.source,
        "source_url": event.source_url,
        "source_title": event.source_title,
        "event_metadata": event.event_metadata_json or {},
        "created_at": event.created_at.isoformat() if event.created_at else None,
        "updated_at": event.updated_at.isoformat() if event.updated_at else None,
    }


def _snapshot_to_dict(snapshot: EarningsRiskSnapshot) -> dict[str, Any]:
    return {
        "id": snapshot.id,
        "symbol": snapshot.symbol,
        "snapshot_date": snapshot.snapshot_date.isoformat()
        if snapshot.snapshot_date is not None
        else None,
        "next_earnings_datetime_utc": snapshot.next_earnings_datetime_utc.isoformat()
        if snapshot.next_earnings_datetime_utc is not None
        else None,
        "days_to_earnings": snapshot.days_to_earnings,
        "earnings_within_window": snapshot.earnings_within_window,
        "earnings_risk_window_days": snapshot.earnings_risk_window_days,
        "earnings_before_expiration": snapshot.earnings_before_expiration,
        "manual_option_expiration_date": snapshot.manual_option_expiration_date.isoformat()
        if snapshot.manual_option_expiration_date is not None
        else None,
        "risk_label": snapshot.risk_label,
        "risk_reason": snapshot.risk_reason,
        "data_sufficiency_status": snapshot.data_sufficiency_status,
        "created_at": snapshot.created_at.isoformat() if snapshot.created_at else None,
        "updated_at": snapshot.updated_at.isoformat() if snapshot.updated_at else None,
    }


@router.get("/events")
def list_earnings_events(
    symbol: str | None = None,
    since: datetime | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(get_db_session),
) -> dict[str, Any]:
    _ensure_tables(session)

    query = session.query(EarningsEvent)

    if symbol is not None:
        query = query.filter(EarningsEvent.symbol == symbol.upper())

    if since is not None:
        query = query.filter(EarningsEvent.earnings_datetime_utc >= since)

    events = (
        query.order_by(EarningsEvent.earnings_datetime_utc.asc(), EarningsEvent.id.asc())
        .limit(limit)
        .all()
    )

    return {
        "status": "OK",
        "count": len(events),
        "events": [_event_to_dict(e) for e in events],
    }


@router.get("/risk-snapshots")
def list_earnings_risk_snapshots(
    symbol: str | None = None,
    since: date | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(get_db_session),
) -> dict[str, Any]:
    _ensure_tables(session)

    query = session.query(EarningsRiskSnapshot)

    if symbol is not None:
        query = query.filter(EarningsRiskSnapshot.symbol == symbol.upper())

    if since is not None:
        query = query.filter(EarningsRiskSnapshot.snapshot_date >= since)

    snapshots = (
        query.order_by(
            EarningsRiskSnapshot.snapshot_date.desc(),
            EarningsRiskSnapshot.id.desc(),
        )
        .limit(limit)
        .all()
    )

    return {
        "status": "OK",
        "count": len(snapshots),
        "snapshots": [_snapshot_to_dict(s) for s in snapshots],
    }


@router.get("/risk-snapshots/latest")
def get_latest_earnings_risk_snapshot(
    symbol: str,
    session: Session = Depends(get_db_session),
) -> dict[str, Any]:
    _ensure_tables(session)

    clean_symbol = symbol.strip().upper()
    if not clean_symbol:
        raise HTTPException(status_code=400, detail="symbol is required.")

    snapshot = (
        session.query(EarningsRiskSnapshot)
        .filter(EarningsRiskSnapshot.symbol == clean_symbol)
        .order_by(
            EarningsRiskSnapshot.snapshot_date.desc(),
            EarningsRiskSnapshot.id.desc(),
        )
        .first()
    )

    if snapshot is None:
        return {
            "status": "OK",
            "symbol": clean_symbol,
            "snapshot": None,
            "data_sufficiency_status": "EARNINGS_DATA_NOT_AVAILABLE",
            "reason": "No earnings risk snapshot has been computed for this symbol yet.",
        }

    return {
        "status": "OK",
        "symbol": clean_symbol,
        "snapshot": _snapshot_to_dict(snapshot),
        "data_sufficiency_status": snapshot.data_sufficiency_status,
    }
