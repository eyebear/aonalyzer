"""Phase 46 — versioning & governance API surface."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy.orm import Session

from app.database.connection import get_db_session
from app.governance.version_models import DecisionAuditMetadata
from app.governance.version_service import GovernanceService, compatibility_check

router = APIRouter(prefix="/api/governance", tags=["governance"])


@router.post("/seed-versions")
def seed_versions(db: Session = Depends(get_db_session)) -> dict[str, Any]:
    created = GovernanceService().seed_initial_versions(db=db)
    return {"status": "OK", "created": created}


@router.post("/compatibility-check")
def check_compatibility(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
    result = compatibility_check(payload.get("version_stamp"))
    return {"status": "OK", "result": result.to_dict()}


@router.get("/audit")
def list_audit(
    symbol: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    GovernanceService().ensure_tables(db)
    q = db.query(DecisionAuditMetadata)
    if symbol is not None:
        q = q.filter(DecisionAuditMetadata.symbol == symbol.strip().upper())
    rows = q.order_by(DecisionAuditMetadata.snapshot_date.desc()).limit(limit).all()
    return {
        "status": "OK",
        "count": len(rows),
        "audit": [
            {
                "symbol": r.symbol,
                "snapshot_date": r.snapshot_date.isoformat() if r.snapshot_date else None,
                "version_stamp": r.version_stamp_json or {},
                "is_compatible": r.is_compatible,
                "missing_version_keys": r.missing_version_keys_json or [],
            }
            for r in rows
        ],
    }
