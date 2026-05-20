from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database.connection import get_db_session
from app.options.manual_option_input_service import ManualOptionInputService

router = APIRouter(tags=["manual-options"])


class ManualOptionInputRequest(BaseModel):
    raw_text: str = Field(min_length=1)
    symbol: str | None = None
    source_name: str | None = None


class ManualOptionSnapshotResponse(BaseModel):
    status: str
    snapshot: dict[str, Any]


class ManualOptionSnapshotListResponse(BaseModel):
    status: str
    snapshots: list[dict[str, Any]]
    count: int


class ManualOptionAnalyzeResponse(BaseModel):
    status: str
    snapshot: dict[str, Any]


@router.post("/api/options/manual-input", response_model=ManualOptionSnapshotResponse)
def create_manual_option_input(
    request: ManualOptionInputRequest,
    session: Session = Depends(get_db_session),
) -> ManualOptionSnapshotResponse:
    service = ManualOptionInputService()

    snapshot = service.create_manual_snapshot(
        db=session,
        raw_text=request.raw_text,
        symbol=request.symbol,
        source_name=request.source_name,
    )

    return ManualOptionSnapshotResponse(
        status="OK",
        snapshot=snapshot.to_dict(),
    )


@router.post(
    "/api/tickers/{symbol}/options/manual-input",
    response_model=ManualOptionSnapshotResponse,
)
def create_ticker_manual_option_input(
    symbol: str,
    request: ManualOptionInputRequest,
    session: Session = Depends(get_db_session),
) -> ManualOptionSnapshotResponse:
    service = ManualOptionInputService()

    snapshot = service.create_manual_snapshot(
        db=session,
        raw_text=request.raw_text,
        symbol=symbol,
        source_name=request.source_name,
    )

    return ManualOptionSnapshotResponse(
        status="OK",
        snapshot=snapshot.to_dict(),
    )


@router.get(
    "/api/options/manual-snapshots",
    response_model=ManualOptionSnapshotListResponse,
)
def list_manual_option_snapshots(
    symbol: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(get_db_session),
) -> ManualOptionSnapshotListResponse:
    service = ManualOptionInputService()

    snapshots = service.list_manual_snapshots(
        db=session,
        symbol=symbol,
        limit=limit,
    )

    return ManualOptionSnapshotListResponse(
        status="OK",
        snapshots=[
            snapshot.to_dict()
            for snapshot in snapshots
        ],
        count=len(snapshots),
    )


@router.post(
    "/api/options/manual-snapshots/{snapshot_id}/analyze",
    response_model=ManualOptionAnalyzeResponse,
)
def analyze_manual_option_snapshot(
    snapshot_id: int,
    session: Session = Depends(get_db_session),
) -> ManualOptionAnalyzeResponse:
    service = ManualOptionInputService()

    try:
        snapshot = service.analyze_manual_snapshot(
            db=session,
            snapshot_id=snapshot_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return ManualOptionAnalyzeResponse(
        status="OK",
        snapshot=snapshot.to_dict(),
    )


@router.get("/api/options/manual-routes-debug")
def manual_option_routes_debug() -> dict[str, Any]:
    return {
        "status": "OK",
        "routes": [
            "POST /api/options/manual-input",
            "POST /api/tickers/{symbol}/options/manual-input",
            "GET /api/options/manual-snapshots",
            "POST /api/options/manual-snapshots/{snapshot_id}/analyze",
        ],
    }