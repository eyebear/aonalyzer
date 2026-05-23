"""Phase 48 — memory export / import API surface."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.database.connection import get_db_session
from app.export_import.exporter import MemoryExporter
from app.export_import.importer import MemoryImporter
from app.export_import.memory_package import validate_package

router = APIRouter(prefix="/api/export-import", tags=["export-import"])


@router.post("/export")
def export_memory(
    payload: dict[str, Any] = Body(default_factory=dict),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    out = payload.get("output_dir")
    if not out:
        settings = get_settings()
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out = str(Path(settings.exports_dir) / f"aonalyzer_memory_{stamp}")
    result = MemoryExporter().export(db=db, output_dir=out)
    return {"status": "OK", "result": result.to_dict()}


@router.post("/validate")
def validate(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
    package_dir = payload.get("package_dir")
    if not package_dir:
        raise HTTPException(status_code=400, detail="package_dir is required.")
    result = validate_package(package_dir)
    return {"status": "OK", "validation": result.to_dict()}


@router.post("/import")
def import_memory(
    payload: dict[str, Any] = Body(default_factory=dict),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    package_dir = payload.get("package_dir")
    if not package_dir:
        raise HTTPException(status_code=400, detail="package_dir is required.")
    result = MemoryImporter().import_package(db=db, package_dir=package_dir)
    return {"status": "OK", "result": result.to_dict()}
