"""Phase 44, steps 44.2-44.13 — weekly learning report generator.

Summarizes recorded outcomes and memory for a period: successes, failures,
stock-right/option-wrong cases, manual option usage, rejected & do-not-touch
outcomes, user overrides, skill performance, and experience usage. Reports only
reflect what was actually tracked — missing option data is reported as missing,
never converted into option success/failure.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.common.service_utils import ensure_tables
from app.learning.learning_report_models import REPORT_WEEKLY, LearningReport
from app.learning.rejection_outcome_models import (
    SOURCE_DO_NOT_TOUCH,
    SOURCE_REJECTION,
    RejectionOutcome,
)
from app.learning.signal_outcome_models import (
    OPTION_OUTCOME_ESTIMATED,
    SignalOutcome,
)
from app.memory.case_memory_models import CASE_STOCK_RIGHT_OPTION_WRONG, CaseMemory
from app.memory.skill_service import SkillService
from app.user_actions.user_action_models import OverrideOutcome


@dataclass
class ReportResult:
    report: LearningReport
    created: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_id": self.report.id,
            "created": self.created,
            "summary": self.report.summary_json,
        }


class LearningReportService:
    def __init__(self, skill_service: SkillService | None = None) -> None:
        self.skill_service = skill_service or SkillService()

    def ensure_tables(self, db: Session) -> None:
        ensure_tables(db)

    def generate_weekly_report(
        self,
        db: Session,
        *,
        period_end: date | None = None,
        now: datetime | None = None,
    ) -> ReportResult:
        self.ensure_tables(db)
        now = now or datetime.now(timezone.utc)
        period_end = period_end or now.date()
        period_start = period_end - timedelta(days=7)

        summary = self._build_summary(db, period_start, period_end)

        existing = (
            db.query(LearningReport)
            .filter(LearningReport.report_type == REPORT_WEEKLY)
            .filter(LearningReport.period_start == period_start)
            .filter(LearningReport.period_end == period_end)
            .one_or_none()
        )
        if existing is None:
            report = LearningReport(
                report_type=REPORT_WEEKLY,
                period_start=period_start,
                period_end=period_end,
                summary_json=summary,
            )
            db.add(report)
            db.commit()
            db.refresh(report)
            return ReportResult(report=report, created=True)

        existing.summary_json = summary
        db.commit()
        db.refresh(existing)
        return ReportResult(report=existing, created=False)

    def _build_summary(
        self, db: Session, start: date, end: date
    ) -> dict[str, Any]:
        signals = (
            db.query(SignalOutcome)
            .filter(SignalOutcome.signal_date >= start)
            .filter(SignalOutcome.signal_date <= end)
            .all()
        )
        evaluated = [s for s in signals if s.price_data_available]
        successes = [s for s in evaluated if s.target_hit]
        failures = [s for s in evaluated if s.stop_hit]
        manual_option_signals = [
            s for s in evaluated if s.option_outcome_status == OPTION_OUTCOME_ESTIMATED
        ]

        rejections = db.query(RejectionOutcome).filter(
            RejectionOutcome.snapshot_date >= start,
            RejectionOutcome.snapshot_date <= end,
        ).all()
        rej_only = [r for r in rejections if r.source_type == SOURCE_REJECTION]
        dnt_only = [r for r in rejections if r.source_type == SOURCE_DO_NOT_TOUCH]

        overrides = db.query(OverrideOutcome).all()
        srow_cases = (
            db.query(CaseMemory)
            .filter(CaseMemory.case_type == CASE_STOCK_RIGHT_OPTION_WRONG)
            .count()
        )
        memory_cases_total = db.query(CaseMemory).count()

        skill_perf = [
            {
                "skill_name": p.skill_name,
                "sample_size": p.sample_size,
                "target_hit_rate": p.target_hit_rate,
                "stock_right_option_wrong_rate": p.stock_right_option_wrong_rate,
                "expected_value_proxy": p.expected_value_proxy,
            }
            for p in self.skill_service.latest_performance(db)
        ]

        return {
            "period_start": start.isoformat(),
            "period_end": end.isoformat(),
            "signals": {
                "total": len(signals),
                "evaluated": len(evaluated),
                "successes_target_hit": len(successes),
                "failures_stop_hit": len(failures),
            },
            "stock_right_option_wrong_cases": srow_cases,
            "manual_option_input_usage": {
                "signals_with_option_outcome": len(manual_option_signals),
                "note": (
                    "Signals without manual option data are reported as missing, "
                    "never as option success or failure."
                ),
            },
            "rejected_outcomes": {
                "total": len(rej_only),
                "correct": sum(1 for r in rej_only if r.was_rejection_correct),
                "too_strict": sum(1 for r in rej_only if r.is_too_strict),
            },
            "do_not_touch_outcomes": {
                "total": len(dnt_only),
                "correct": sum(1 for r in dnt_only if r.was_rejection_correct),
                "too_strict": sum(1 for r in dnt_only if r.is_too_strict),
            },
            "user_overrides": {
                "total": len(overrides),
                "user_right": sum(
                    1 for o in overrides if o.outcome_classification == "USER_RIGHT"
                ),
                "system_right": sum(
                    1 for o in overrides if o.outcome_classification == "SYSTEM_RIGHT"
                ),
                "missed_opportunities": sum(1 for o in overrides if o.is_missed_opportunity),
                "avoided_correctly": sum(1 for o in overrides if o.is_avoided_correctly),
            },
            "skill_performance": skill_perf,
            "experience_usage": {
                "memory_cases_total": memory_cases_total,
            },
        }

    def list_reports(self, db: Session, *, limit: int = 50) -> list[LearningReport]:
        self.ensure_tables(db)
        return (
            db.query(LearningReport)
            .order_by(LearningReport.period_end.desc(), LearningReport.id.desc())
            .limit(limit)
            .all()
        )


__all__ = ["LearningReportService", "ReportResult"]
