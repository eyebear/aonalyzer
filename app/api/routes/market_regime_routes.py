from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.common.service_utils import ensure_tables
from app.database.connection import get_db_session
from app.market_regime.market_regime_models import (
    MarketRegimeSnapshot,
    SectorStrengthSnapshot,
)

router = APIRouter(prefix="/api/market-regime", tags=["market-regime"])


def _ensure_tables(session: Session) -> None:
    ensure_tables(session)


def _regime_to_dict(snapshot: MarketRegimeSnapshot) -> dict[str, Any]:
    return {
        "id": snapshot.id,
        "snapshot_date": snapshot.snapshot_date.isoformat()
        if snapshot.snapshot_date is not None
        else None,
        "source": snapshot.source,
        "source_record_count": snapshot.source_record_count,
        "indexes": {
            "spy": {"close": snapshot.spy_close, "trend": snapshot.spy_trend},
            "qqq": {"close": snapshot.qqq_close, "trend": snapshot.qqq_trend},
            "iwm": {"close": snapshot.iwm_close, "trend": snapshot.iwm_trend},
            "uptrend_count": snapshot.index_uptrend_count,
            "downtrend_count": snapshot.index_downtrend_count,
        },
        "vix": {
            "symbol": snapshot.vix_symbol,
            "level": snapshot.vix_level,
            "state": snapshot.vix_state,
        },
        "yield": {
            "symbol": snapshot.yield_symbol,
            "level": snapshot.yield_level,
            "change_pct": snapshot.yield_change_pct,
            "state": snapshot.yield_state,
            "pressure": snapshot.yield_pressure,
        },
        "regime": {
            "label": snapshot.regime_label,
            "score": snapshot.regime_score,
        },
        "data_sufficiency_status": snapshot.data_sufficiency_status,
        "insufficient_reasons": snapshot.insufficient_reasons_json or [],
        "notes": snapshot.notes,
        "created_at": snapshot.created_at.isoformat() if snapshot.created_at else None,
        "updated_at": snapshot.updated_at.isoformat() if snapshot.updated_at else None,
    }


def _sector_to_dict(snapshot: SectorStrengthSnapshot) -> dict[str, Any]:
    return {
        "id": snapshot.id,
        "snapshot_date": snapshot.snapshot_date.isoformat()
        if snapshot.snapshot_date is not None
        else None,
        "sector_symbol": snapshot.sector_symbol,
        "benchmark_symbol": snapshot.benchmark_symbol,
        "lookback_days": snapshot.lookback_days,
        "sector_return_pct": snapshot.sector_return_pct,
        "benchmark_return_pct": snapshot.benchmark_return_pct,
        "relative_strength": snapshot.relative_strength,
        "rs_rank": snapshot.rs_rank,
        "trend": snapshot.trend,
        "data_sufficiency_status": snapshot.data_sufficiency_status,
        "insufficient_reasons": snapshot.insufficient_reasons_json or [],
        "created_at": snapshot.created_at.isoformat() if snapshot.created_at else None,
        "updated_at": snapshot.updated_at.isoformat() if snapshot.updated_at else None,
    }


@router.get("")
def list_market_regimes(
    since: date | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(get_db_session),
) -> dict[str, Any]:
    _ensure_tables(session)

    query = session.query(MarketRegimeSnapshot)
    if since is not None:
        query = query.filter(MarketRegimeSnapshot.snapshot_date >= since)

    snapshots = (
        query.order_by(MarketRegimeSnapshot.snapshot_date.desc(), MarketRegimeSnapshot.id.desc())
        .limit(limit)
        .all()
    )

    return {
        "status": "OK",
        "count": len(snapshots),
        "regimes": [_regime_to_dict(s) for s in snapshots],
    }


@router.get("/latest")
def get_latest_market_regime(
    session: Session = Depends(get_db_session),
) -> dict[str, Any]:
    _ensure_tables(session)

    snapshot = (
        session.query(MarketRegimeSnapshot)
        .order_by(MarketRegimeSnapshot.snapshot_date.desc(), MarketRegimeSnapshot.id.desc())
        .first()
    )

    if snapshot is None:
        return {
            "status": "OK",
            "regime": None,
            "data_sufficiency_status": "INSUFFICIENT_PRICE_HISTORY",
            "reason": "No market-regime snapshot has been computed yet.",
        }

    return {
        "status": "OK",
        "data_sufficiency_status": snapshot.data_sufficiency_status,
        "regime": _regime_to_dict(snapshot),
    }


@router.get("/sectors")
def get_sector_strength(
    snapshot_date: date | None = None,
    benchmark: str | None = None,
    session: Session = Depends(get_db_session),
) -> dict[str, Any]:
    _ensure_tables(session)

    target_date = snapshot_date
    if target_date is None:
        latest = (
            session.query(SectorStrengthSnapshot.snapshot_date)
            .order_by(SectorStrengthSnapshot.snapshot_date.desc())
            .first()
        )
        target_date = latest[0] if latest is not None else None

    if target_date is None:
        return {
            "status": "OK",
            "snapshot_date": None,
            "count": 0,
            "sectors": [],
            "reason": "No sector-strength snapshot has been computed yet.",
        }

    query = session.query(SectorStrengthSnapshot).filter(
        SectorStrengthSnapshot.snapshot_date == target_date
    )
    if benchmark is not None:
        query = query.filter(SectorStrengthSnapshot.benchmark_symbol == benchmark.upper())

    sectors = query.order_by(
        SectorStrengthSnapshot.benchmark_symbol.asc(),
        SectorStrengthSnapshot.rs_rank.asc().nullslast(),
        SectorStrengthSnapshot.sector_symbol.asc(),
    ).all()

    return {
        "status": "OK",
        "snapshot_date": target_date.isoformat(),
        "count": len(sectors),
        "sectors": [_sector_to_dict(s) for s in sectors],
    }
