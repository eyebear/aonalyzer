from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.common.service_utils import ensure_tables
from app.data_quality.data_quality_models import DataFreshness
from app.database.connection import SessionLocal
from app.market_data.market_data_models import (
    DailyPrice,
    FailedTickerLog,
    IntradayPrice,
)

router = APIRouter(prefix="/api/agent", tags=["market-data"])


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_market_data_tables(db: Session) -> None:
    # Test/dev fallback only — no-op on PostgreSQL (schema owned by Alembic).
    # Binds to the request session's engine so dependency-overridden test
    # sessions are honored instead of the module-level production engine.
    ensure_tables(db)


@router.get("/market-data/daily-prices")
def get_daily_prices(
    symbol: str | None = None,
    limit: int = 200,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    ensure_market_data_tables(db)

    query = db.query(DailyPrice)

    if symbol:
        query = query.filter(DailyPrice.symbol == symbol.upper())

    rows = (
        query.order_by(DailyPrice.price_date.desc())
        .limit(limit)
        .all()
    )

    return {
        "status": "OK",
        "daily_prices": [
            {
                "id": row.id,
                "symbol": row.symbol,
                "price_date": row.price_date.isoformat()
                if row.price_date
                else None,
                "open": float(row.open_price) if row.open_price is not None else None,
                "high": float(row.high_price) if row.high_price is not None else None,
                "low": float(row.low_price) if row.low_price is not None else None,
                "close": float(row.close_price) if row.close_price is not None else None,
                "adjusted_close": float(row.adjusted_close_price)
                if row.adjusted_close_price is not None
                else None,
                "volume": row.volume,
                "source": row.source,
            }
            for row in rows
        ],
    }


@router.get("/market-data/intraday-prices")
def get_intraday_prices(
    symbol: str | None = None,
    limit: int = 200,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    ensure_market_data_tables(db)

    query = db.query(IntradayPrice)

    if symbol:
        query = query.filter(IntradayPrice.symbol == symbol.upper())

    rows = (
        query.order_by(IntradayPrice.price_time.desc())
        .limit(limit)
        .all()
    )

    return {
        "status": "OK",
        "intraday_prices": [
            {
                "id": row.id,
                "symbol": row.symbol,
                "price_time": row.price_time.isoformat()
                if row.price_time
                else None,
                "interval": row.interval,
                "open": float(row.open_price) if row.open_price is not None else None,
                "high": float(row.high_price) if row.high_price is not None else None,
                "low": float(row.low_price) if row.low_price is not None else None,
                "close": float(row.close_price) if row.close_price is not None else None,
                "adjusted_close": None,
                "volume": row.volume,
                "source": row.source,
            }
            for row in rows
        ],
    }


@router.get("/market-data/failed-tickers")
def get_failed_ticker_logs(
    limit: int = 100,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    ensure_market_data_tables(db)

    rows = (
        db.query(FailedTickerLog)
        .order_by(FailedTickerLog.created_at.desc())
        .limit(limit)
        .all()
    )

    return {
        "status": "OK",
        "failed_tickers": [
            {
                "id": row.id,
                "symbol": row.symbol,
                "data_category": row.data_category,
                "source": row.source,
                "reason": row.reason,
                "created_at": row.created_at.isoformat()
                if row.created_at
                else None,
            }
            for row in rows
        ],
    }


@router.get("/market-data/freshness")
def get_market_data_freshness(
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    ensure_market_data_tables(db)

    row = (
        db.query(DataFreshness)
        .filter(DataFreshness.data_category == "market_data")
        .one_or_none()
    )

    if row is None:
        return {
            "status": "OK",
            "freshness": None,
        }

    return {
        "status": "OK",
        "freshness": {
            "data_category": row.data_category,
            "latest_success_at": row.latest_success_at.isoformat()
            if row.latest_success_at
            else None,
            "freshness_status": row.freshness_status,
            "max_age_minutes": row.max_age_minutes,
            "last_checked_at": row.last_checked_at.isoformat()
            if row.last_checked_at
            else None,
            "details": row.details_json or {},
        },
    }