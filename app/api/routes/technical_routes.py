from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.base import Base
from app.database.connection import get_db_session
from app.quant.technical_snapshot_models import TechnicalSnapshot


router = APIRouter(prefix="/api/technical", tags=["technical"])


def _ensure_technical_table(session: Session) -> None:
    Base.metadata.create_all(bind=session.get_bind())


def _snapshot_to_dict(snapshot: TechnicalSnapshot) -> dict[str, Any]:
    return {
        "id": snapshot.id,
        "symbol": snapshot.symbol,
        "snapshot_date": snapshot.snapshot_date.isoformat()
        if snapshot.snapshot_date is not None
        else None,
        "source": snapshot.source,
        "source_record_count": snapshot.source_record_count,
        "data_sufficiency_status": snapshot.data_sufficiency_status,
        "insufficient_indicators": snapshot.insufficient_indicators_json or [],
        "indicators": {
            "last_close": snapshot.last_close,
            "last_volume": snapshot.last_volume,
            "sma_20": snapshot.sma_20,
            "sma_50": snapshot.sma_50,
            "sma_200": snapshot.sma_200,
            "ema_12": snapshot.ema_12,
            "ema_26": snapshot.ema_26,
            "rsi_14": snapshot.rsi_14,
            "macd": snapshot.macd,
            "macd_signal": snapshot.macd_signal,
            "macd_histogram": snapshot.macd_histogram,
            "atr_14": snapshot.atr_14,
            "bollinger_upper": snapshot.bollinger_upper,
            "bollinger_middle": snapshot.bollinger_middle,
            "bollinger_lower": snapshot.bollinger_lower,
            "volume_ratio_20": snapshot.volume_ratio_20,
        },
        "notes": snapshot.notes,
        "created_at": snapshot.created_at.isoformat()
        if snapshot.created_at is not None
        else None,
        "updated_at": snapshot.updated_at.isoformat()
        if snapshot.updated_at is not None
        else None,
    }


@router.get("/snapshots")
def list_technical_snapshots(
    symbol: str | None = None,
    since: date | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(get_db_session),
) -> dict[str, Any]:
    _ensure_technical_table(session)

    query = session.query(TechnicalSnapshot)

    if symbol is not None:
        query = query.filter(TechnicalSnapshot.symbol == symbol.upper())

    if since is not None:
        query = query.filter(TechnicalSnapshot.snapshot_date >= since)

    snapshots = (
        query.order_by(
            TechnicalSnapshot.snapshot_date.desc(),
            TechnicalSnapshot.id.desc(),
        )
        .limit(limit)
        .all()
    )

    return {
        "status": "OK",
        "count": len(snapshots),
        "snapshots": [_snapshot_to_dict(s) for s in snapshots],
    }


@router.get("/snapshots/latest")
def get_latest_technical_snapshot(
    symbol: str,
    session: Session = Depends(get_db_session),
) -> dict[str, Any]:
    _ensure_technical_table(session)

    clean_symbol = symbol.strip().upper()
    if not clean_symbol:
        raise HTTPException(status_code=400, detail="symbol is required.")

    snapshot = (
        session.query(TechnicalSnapshot)
        .filter(TechnicalSnapshot.symbol == clean_symbol)
        .order_by(
            TechnicalSnapshot.snapshot_date.desc(),
            TechnicalSnapshot.id.desc(),
        )
        .first()
    )

    if snapshot is None:
        return {
            "status": "OK",
            "symbol": clean_symbol,
            "snapshot": None,
            "data_sufficiency_status": "INSUFFICIENT_PRICE_HISTORY",
            "reason": "No technical snapshot has been computed for this symbol yet.",
        }

    return {
        "status": "OK",
        "symbol": clean_symbol,
        "snapshot": _snapshot_to_dict(snapshot),
        "data_sufficiency_status": snapshot.data_sufficiency_status,
    }
