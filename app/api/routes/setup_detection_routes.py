from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.common.service_utils import ensure_tables
from app.database.connection import get_db_session
from app.setup_detection.setup_detection_models import StockSetupSignal

router = APIRouter(prefix="/api/setup-signals", tags=["setup-signals"])


def _ensure_tables(session: Session) -> None:
    ensure_tables(session)


def _signal_to_dict(signal: StockSetupSignal) -> dict[str, Any]:
    return {
        "id": signal.id,
        "symbol": signal.symbol,
        "snapshot_date": signal.snapshot_date.isoformat()
        if signal.snapshot_date is not None
        else None,
        "source": signal.source,
        "setup_type": signal.setup_type,
        "direction": signal.direction,
        "score": signal.score,
        "inputs": {
            "close": signal.close,
            "rsi_14": signal.rsi_14,
            "atr_14": signal.atr_14,
            "risk_reward": signal.risk_reward,
            "nearest_support": signal.nearest_support,
            "nearest_resistance": signal.nearest_resistance,
            "entry_zone_low": signal.entry_zone_low,
            "entry_zone_high": signal.entry_zone_high,
            "target_price": signal.target_price,
            "stop_price": signal.stop_price,
            "regime_label": signal.regime_label,
            "sector_symbol": signal.sector_symbol,
            "sector_trend": signal.sector_trend,
            "sector_rs_rank": signal.sector_rs_rank,
        },
        "data_sufficiency_status": signal.data_sufficiency_status,
        "reasons": signal.reasons_json or [],
        "components": signal.components_json or {},
        "notes": signal.notes,
        "created_at": signal.created_at.isoformat() if signal.created_at else None,
        "updated_at": signal.updated_at.isoformat() if signal.updated_at else None,
    }


@router.get("")
def list_setup_signals(
    symbol: str | None = None,
    setup_type: str | None = None,
    since: date | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(get_db_session),
) -> dict[str, Any]:
    _ensure_tables(session)

    query = session.query(StockSetupSignal)
    if symbol is not None:
        query = query.filter(StockSetupSignal.symbol == symbol.upper())
    if setup_type is not None:
        query = query.filter(StockSetupSignal.setup_type == setup_type.upper())
    if since is not None:
        query = query.filter(StockSetupSignal.snapshot_date >= since)

    signals = (
        query.order_by(StockSetupSignal.snapshot_date.desc(), StockSetupSignal.id.desc())
        .limit(limit)
        .all()
    )

    return {
        "status": "OK",
        "count": len(signals),
        "signals": [_signal_to_dict(s) for s in signals],
    }


@router.get("/latest")
def get_latest_setup_signal(
    symbol: str,
    session: Session = Depends(get_db_session),
) -> dict[str, Any]:
    _ensure_tables(session)

    clean_symbol = symbol.strip().upper()
    if not clean_symbol:
        raise HTTPException(status_code=400, detail="symbol is required.")

    signal = (
        session.query(StockSetupSignal)
        .filter(StockSetupSignal.symbol == clean_symbol)
        .order_by(StockSetupSignal.snapshot_date.desc(), StockSetupSignal.id.desc())
        .first()
    )

    if signal is None:
        return {
            "status": "OK",
            "symbol": clean_symbol,
            "signal": None,
            "data_sufficiency_status": "INSUFFICIENT_INPUT",
            "reason": "No setup signal has been detected for this symbol yet.",
        }

    return {
        "status": "OK",
        "symbol": clean_symbol,
        "data_sufficiency_status": signal.data_sufficiency_status,
        "signal": _signal_to_dict(signal),
    }
