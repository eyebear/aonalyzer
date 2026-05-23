"""Phase 47 — platform settings API surface (coexists with profile routes)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.connection import get_db_session
from app.governance.settings_service import SETTING_SPECS, SettingsService

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("/platform")
def get_platform_settings(db: Session = Depends(get_db_session)) -> dict[str, Any]:
    return {"status": "OK", "settings": SettingsService().get_all(db=db)}


@router.post("/platform")
def set_platform_settings(
    payload: dict[str, Any] = Body(default_factory=dict),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    unknown = [k for k in payload if k not in SETTING_SPECS]
    if unknown:
        raise HTTPException(status_code=400, detail=f"unknown settings: {unknown}")
    settings = SettingsService().set_many(db=db, values=payload)
    return {"status": "OK", "settings": settings}


@router.post("/platform/reset")
def reset_platform_settings(
    key: str | None = Query(default=None),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    try:
        settings = SettingsService().reset(db=db, key=key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "OK", "settings": settings}
