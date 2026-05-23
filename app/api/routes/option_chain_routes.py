"""Phase 8 placeholder routes.

These endpoints remain available, but real option-chain snapshot storage is
disabled until a real provider is selected.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.connection import get_db_session

router = APIRouter(tags=["option-chain"])


@router.get("/api/options/snapshots")
def get_option_chain_snapshots(
    symbol: str | None = None,
    limit: int = 200,
    session: Session = Depends(get_db_session),
) -> dict[str, Any]:
    return {
        "status": "OK",
        "placeholder": True,
        "message": (
            "Automatic option-chain collection is not enabled, so no option "
            "snapshots are stored. Paste option contract data manually to "
            "evaluate the option side."
        ),
        "symbol": symbol.upper() if symbol else None,
        "limit": limit,
        "snapshots": [],
    }


@router.get("/api/options/freshness")
def get_option_chain_freshness(
    session: Session = Depends(get_db_session),
) -> dict[str, Any]:
    return {
        "status": "OK",
        "placeholder": True,
        "message": (
            "No automatic option-chain provider is active, so option-chain "
            "freshness is not tracked."
        ),
        "freshness": None,
    }