from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.base import Base
from app.database.connection import get_db_session
from app.quant.stock_setup_models import StockSetup

router = APIRouter(prefix="/api/setups", tags=["setups"])


def _ensure_tables(session: Session) -> None:
    Base.metadata.create_all(bind=session.get_bind())


def _setup_to_dict(setup: StockSetup) -> dict[str, Any]:
    return {
        "id": setup.id,
        "symbol": setup.symbol,
        "snapshot_date": setup.snapshot_date.isoformat()
        if setup.snapshot_date is not None
        else None,
        "source": setup.source,
        "source_record_count": setup.source_record_count,
        "current_close": setup.current_close,
        "levels": {
            "nearest_support": setup.nearest_support,
            "nearest_resistance": setup.nearest_resistance,
            "swing_low": setup.swing_low,
            "swing_high": setup.swing_high,
        },
        "cached_indicators": {
            "sma_20": setup.sma_20,
            "sma_50": setup.sma_50,
            "sma_200": setup.sma_200,
            "atr_14": setup.atr_14,
        },
        "setup": {
            "direction": setup.direction,
            "entry_zone_low": setup.entry_zone_low,
            "entry_zone_high": setup.entry_zone_high,
            "target_price": setup.target_price,
            "stop_price": setup.stop_price,
            "stop_method": setup.stop_method,
            "risk_per_share": setup.risk_per_share,
            "reward_per_share": setup.reward_per_share,
            "stock_risk_reward": setup.stock_risk_reward,
        },
        "data_sufficiency_status": setup.data_sufficiency_status,
        "insufficient_reasons": setup.insufficient_reasons_json or [],
        "notes": setup.notes,
        "created_at": setup.created_at.isoformat() if setup.created_at else None,
        "updated_at": setup.updated_at.isoformat() if setup.updated_at else None,
    }


@router.get("")
def list_stock_setups(
    symbol: str | None = None,
    since: date | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(get_db_session),
) -> dict[str, Any]:
    _ensure_tables(session)

    query = session.query(StockSetup)

    if symbol is not None:
        query = query.filter(StockSetup.symbol == symbol.upper())

    if since is not None:
        query = query.filter(StockSetup.snapshot_date >= since)

    setups = (
        query.order_by(StockSetup.snapshot_date.desc(), StockSetup.id.desc())
        .limit(limit)
        .all()
    )

    return {
        "status": "OK",
        "count": len(setups),
        "setups": [_setup_to_dict(s) for s in setups],
    }


@router.get("/latest")
def get_latest_stock_setup(
    symbol: str,
    session: Session = Depends(get_db_session),
) -> dict[str, Any]:
    _ensure_tables(session)

    clean_symbol = symbol.strip().upper()
    if not clean_symbol:
        raise HTTPException(status_code=400, detail="symbol is required.")

    setup = (
        session.query(StockSetup)
        .filter(StockSetup.symbol == clean_symbol)
        .order_by(StockSetup.snapshot_date.desc(), StockSetup.id.desc())
        .first()
    )

    if setup is None:
        return {
            "status": "OK",
            "symbol": clean_symbol,
            "setup": None,
            "data_sufficiency_status": "INSUFFICIENT_PRICE_HISTORY",
            "reason": "No stock setup has been computed for this symbol yet.",
        }

    return {
        "status": "OK",
        "symbol": clean_symbol,
        "data_sufficiency_status": setup.data_sufficiency_status,
        "setup": _setup_to_dict(setup),
    }
