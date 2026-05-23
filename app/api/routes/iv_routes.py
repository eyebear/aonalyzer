from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.common.service_utils import ensure_tables
from app.database.connection import get_db_session
from app.iv_history.iv_models import IvHistoryDay, IvRiskSnapshot

router = APIRouter(prefix="/api/iv", tags=["iv"])


def _ensure_tables(session: Session) -> None:
    # Test/dev fallback only — no-op on PostgreSQL (schema owned by Alembic).
    ensure_tables(session)


def _history_to_dict(row: IvHistoryDay) -> dict[str, Any]:
    return {
        "id": row.id,
        "symbol": row.symbol,
        "snapshot_date": row.snapshot_date.isoformat()
        if row.snapshot_date is not None
        else None,
        "atm_iv_30d": row.atm_iv_30d,
        "source": row.source,
        "source_url": row.source_url,
        "metadata": row.metadata_json or {},
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _snapshot_to_dict(snapshot: IvRiskSnapshot) -> dict[str, Any]:
    return {
        "id": snapshot.id,
        "symbol": snapshot.symbol,
        "snapshot_date": snapshot.snapshot_date.isoformat()
        if snapshot.snapshot_date is not None
        else None,
        "current_iv": snapshot.current_iv,
        "iv_rank": snapshot.iv_rank,
        "iv_percentile": snapshot.iv_percentile,
        "iv_history_days_used": snapshot.iv_history_days_used,
        "iv_warning_threshold": snapshot.iv_warning_threshold,
        "iv_reject_threshold": snapshot.iv_reject_threshold,
        "risk_label": snapshot.risk_label,
        "risk_reason": snapshot.risk_reason,
        "data_sufficiency_status": snapshot.data_sufficiency_status,
        "created_at": snapshot.created_at.isoformat() if snapshot.created_at else None,
        "updated_at": snapshot.updated_at.isoformat() if snapshot.updated_at else None,
    }


@router.get("/history")
def list_iv_history(
    symbol: str,
    since: date | None = None,
    limit: int = Query(default=500, ge=1, le=2000),
    session: Session = Depends(get_db_session),
) -> dict[str, Any]:
    _ensure_tables(session)

    clean_symbol = symbol.strip().upper()
    if not clean_symbol:
        raise HTTPException(status_code=400, detail="symbol is required.")

    query = session.query(IvHistoryDay).filter(IvHistoryDay.symbol == clean_symbol)

    if since is not None:
        query = query.filter(IvHistoryDay.snapshot_date >= since)

    rows = (
        query.order_by(IvHistoryDay.snapshot_date.desc())
        .limit(limit)
        .all()
    )

    if not rows:
        return {
            "status": "OK",
            "symbol": clean_symbol,
            "count": 0,
            "history": [],
            "data_sufficiency_status": "IV_DATA_NOT_AVAILABLE",
            "reason": "No IV history rows are stored for this symbol.",
        }

    return {
        "status": "OK",
        "symbol": clean_symbol,
        "count": len(rows),
        "history": [_history_to_dict(r) for r in rows],
        "data_sufficiency_status": "SUFFICIENT",
    }


@router.get("/risk-snapshots")
def list_iv_risk_snapshots(
    symbol: str | None = None,
    since: date | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(get_db_session),
) -> dict[str, Any]:
    _ensure_tables(session)

    query = session.query(IvRiskSnapshot)

    if symbol is not None:
        query = query.filter(IvRiskSnapshot.symbol == symbol.upper())

    if since is not None:
        query = query.filter(IvRiskSnapshot.snapshot_date >= since)

    snapshots = (
        query.order_by(
            IvRiskSnapshot.snapshot_date.desc(),
            IvRiskSnapshot.id.desc(),
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
def get_latest_iv_risk_snapshot(
    symbol: str,
    session: Session = Depends(get_db_session),
) -> dict[str, Any]:
    _ensure_tables(session)

    clean_symbol = symbol.strip().upper()
    if not clean_symbol:
        raise HTTPException(status_code=400, detail="symbol is required.")

    snapshot = (
        session.query(IvRiskSnapshot)
        .filter(IvRiskSnapshot.symbol == clean_symbol)
        .order_by(
            IvRiskSnapshot.snapshot_date.desc(),
            IvRiskSnapshot.id.desc(),
        )
        .first()
    )

    if snapshot is None:
        return {
            "status": "OK",
            "symbol": clean_symbol,
            "snapshot": None,
            "data_sufficiency_status": "IV_DATA_NOT_AVAILABLE",
            "reason": "No IV risk snapshot has been computed for this symbol yet.",
        }

    return {
        "status": "OK",
        "symbol": clean_symbol,
        "snapshot": _snapshot_to_dict(snapshot),
        "data_sufficiency_status": snapshot.data_sufficiency_status,
    }
