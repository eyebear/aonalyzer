"""Phases 44-45 — learning reports + improvement engine API surface."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.connection import get_db_session
from app.learning.champion_challenger import RuleArm, compare_rule_versions
from app.learning.improvement_engine import ImprovementEngine
from app.learning.improvement_models import ALL_STATUSES, ImprovementSuggestion
from app.learning.learning_report_models import LearningReport
from app.learning.learning_report_service import LearningReportService

router = APIRouter(prefix="/api/learning", tags=["learning"])


def _report_to_dict(r: LearningReport) -> dict[str, Any]:
    return {
        "id": r.id,
        "report_type": r.report_type,
        "period_start": r.period_start.isoformat() if r.period_start else None,
        "period_end": r.period_end.isoformat() if r.period_end else None,
        "summary": r.summary_json or {},
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


def _suggestion_to_dict(s: ImprovementSuggestion) -> dict[str, Any]:
    return {
        "id": s.id,
        "suggestion_type": s.suggestion_type,
        "title": s.title,
        "rationale": s.rationale,
        "current_value": s.current_value,
        "proposed_value": s.proposed_value,
        "evidence": s.evidence_json or {},
        "comparison": s.comparison_json or {},
        "status": s.status,
        "decided_at": s.decided_at.isoformat() if s.decided_at else None,
    }


# --- Learning reports ------------------------------------------------------


@router.post("/reports/generate")
def generate_report(db: Session = Depends(get_db_session)) -> dict[str, Any]:
    result = LearningReportService().generate_weekly_report(db=db)
    return {"status": "OK", "result": result.to_dict()}


@router.get("/reports")
def list_reports(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    rows = LearningReportService().list_reports(db=db, limit=limit)
    return {"status": "OK", "count": len(rows), "reports": [_report_to_dict(r) for r in rows]}


# --- Improvement suggestions ------------------------------------------------


@router.post("/improvements/generate")
def generate_improvements(db: Session = Depends(get_db_session)) -> dict[str, Any]:
    result = ImprovementEngine().generate(db=db)
    return {"status": "OK", "result": result.to_dict()}


@router.get("/improvements")
def list_improvements(
    status: str | None = Query(default=None),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    if status is not None and status.upper() not in ALL_STATUSES:
        raise HTTPException(status_code=400, detail=f"unknown status '{status}'.")
    rows = ImprovementEngine().list_suggestions(db=db, status=status)
    return {
        "status": "OK",
        "count": len(rows),
        "suggestions": [_suggestion_to_dict(s) for s in rows],
    }


@router.post("/improvements/{suggestion_id}/decide")
def decide_improvement(
    suggestion_id: int,
    payload: dict[str, Any] = Body(default_factory=dict),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    approve = bool(payload.get("approve", False))
    row = ImprovementEngine().decide(
        db=db, suggestion_id=suggestion_id, approve=approve, decided_by=payload.get("decided_by")
    )
    if row is None:
        raise HTTPException(status_code=404, detail=f"suggestion {suggestion_id} not found.")
    return {"status": "OK", "suggestion": _suggestion_to_dict(row)}


@router.post("/champion-challenger/compare")
def compare(
    payload: dict[str, Any] = Body(default_factory=dict),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    champion = RuleArm(
        name="champion",
        min_risk_reward=float(payload.get("champion_min_risk_reward", 2.0)),
    )
    challenger = RuleArm(
        name="challenger",
        min_risk_reward=float(payload.get("challenger_min_risk_reward", 1.7)),
    )
    result = compare_rule_versions(db, champion=champion, challenger=challenger)
    return {"status": "OK", "comparison": result.to_dict()}
