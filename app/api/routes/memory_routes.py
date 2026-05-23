"""Phases 41-43 — case memory, vector memory, and skill API surface."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy.orm import Session

from app.database.connection import get_db_session
from app.memory.case_memory_models import CaseMemory
from app.memory.case_memory_service import CaseMemoryService
from app.memory.skill_models import SkillPerformance, SkillRegistry
from app.memory.skill_service import SkillService
from app.memory.vector_search_service import VectorSearchService

router = APIRouter(prefix="/api/memory", tags=["memory"])


def _case_to_dict(c: CaseMemory) -> dict[str, Any]:
    return {
        "id": c.id,
        "symbol": c.symbol,
        "case_type": c.case_type,
        "source_type": c.source_type,
        "outcome_type": c.outcome_type,
        "option_data_available": c.option_data_available,
        "lesson_summary": c.lesson_summary,
        "snapshot_date": c.snapshot_date.isoformat() if c.snapshot_date else None,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


# --- Case memory -----------------------------------------------------------


@router.post("/cases/build")
def build_cases(db: Session = Depends(get_db_session)) -> dict[str, Any]:
    result = CaseMemoryService().build_cases(db=db)
    return {"status": "OK", "result": result.to_dict()}


@router.get("/cases")
def list_cases(
    symbol: str | None = Query(default=None),
    case_type: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    rows = CaseMemoryService().list_cases(
        db=db, symbol=symbol, case_type=case_type, limit=limit
    )
    return {"status": "OK", "count": len(rows), "cases": [_case_to_dict(r) for r in rows]}


# --- Vector memory ---------------------------------------------------------


@router.post("/vector/ingest")
def ingest_vectors(db: Session = Depends(get_db_session)) -> dict[str, Any]:
    result = VectorSearchService().ingest_all(db=db)
    return {"status": "OK", "result": result.to_dict()}


@router.post("/vector/search")
def vector_search(
    payload: dict[str, Any] = Body(default_factory=dict),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    query_text = payload.get("query_text", "")
    results = VectorSearchService().search(
        db=db,
        query_text=query_text,
        limit=int(payload.get("limit", 5)),
        source_type=payload.get("source_type"),
        symbol=payload.get("symbol"),
    )
    return {"status": "OK", "count": len(results), "results": results}


# --- Skills ----------------------------------------------------------------


@router.post("/skills/register")
def register_skills(db: Session = Depends(get_db_session)) -> dict[str, Any]:
    created = SkillService().register_initial_skills(db=db)
    return {"status": "OK", "created": created}


@router.post("/skills/compute")
def compute_skill_performance(db: Session = Depends(get_db_session)) -> dict[str, Any]:
    svc = SkillService()
    svc.register_initial_skills(db=db)
    svc.infer_and_link(db=db)
    result = svc.compute_performance(db=db)
    return {"status": "OK", "result": result.to_dict()}


@router.get("/skills")
def list_skills(db: Session = Depends(get_db_session)) -> dict[str, Any]:
    svc = SkillService()
    skills: list[SkillRegistry] = svc.list_skills(db=db)
    perf: list[SkillPerformance] = svc.latest_performance(db=db)
    perf_by_name = {p.skill_name: p for p in perf}
    return {
        "status": "OK",
        "skills": [
            {
                "skill_name": s.skill_name,
                "category": s.category,
                "description": s.description,
                "performance": {
                    "sample_size": perf_by_name[s.skill_name].sample_size,
                    "target_hit_rate": perf_by_name[s.skill_name].target_hit_rate,
                    "stop_first_rate": perf_by_name[s.skill_name].stop_first_rate,
                    "stock_right_option_wrong_rate": perf_by_name[
                        s.skill_name
                    ].stock_right_option_wrong_rate,
                    "manual_option_reader_usefulness": perf_by_name[
                        s.skill_name
                    ].manual_option_reader_usefulness,
                    "expected_value_proxy": perf_by_name[s.skill_name].expected_value_proxy,
                }
                if s.skill_name in perf_by_name
                else None,
            }
            for s in skills
        ],
    }
