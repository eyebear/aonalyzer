"""Phase 28, step 28.2 — One-Page Ticker Brief service.

DB-facing workflow that *assembles* a brief from existing layers:

* the canonical decision (``DecisionService``) for thesis / option-expression
  detail, trace, confidence breakdown, and version stamp;
* the canonical action package (``ActionSuggestionService``) for the final
  action label, summary, lifecycle state, scope, and manual-option needs;
* persisted earnings / IV risk snapshots and recent events;
* the presence (and missing fields) of a manual option snapshot.

It never recomputes decisions outside these services and never invents absent
values. The brief is upserted into ``ticker_briefs``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.action.action_service import ActionSuggestionService
from app.brief.ticker_brief_builder import (
    BriefInputs,
    TickerBriefResult,
    build_ticker_brief,
)
from app.brief.ticker_brief_models import TickerBrief
from app.common.service_utils import ensure_tables
from app.core.config import AppSettings, get_settings
from app.database.models import Event
from app.decision.decision_service import DecisionService
from app.earnings.earnings_models import EarningsRiskSnapshot
from app.iv_history.iv_models import IvRiskSnapshot
from app.options.manual_option_input_service import ManualOptionInputService
from app.options.manual_option_models import ManualOptionSnapshotRecord
from app.profiles.profile_models import StrategyProfile


@dataclass
class BriefEvaluation:
    brief: TickerBriefResult
    record: TickerBrief | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "brief": self.brief.to_dict(),
            "record_id": self.record.id if self.record is not None else None,
        }


class TickerBriefService:
    def __init__(
        self,
        settings: AppSettings | None = None,
        decision_service: DecisionService | None = None,
        action_service: ActionSuggestionService | None = None,
        manual_option_service: ManualOptionInputService | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.decision_service = decision_service or DecisionService(settings=self.settings)
        self.action_service = action_service or ActionSuggestionService(
            settings=self.settings, decision_service=self.decision_service
        )
        self.manual_option_service = manual_option_service or ManualOptionInputService()

    def ensure_tables(self, db: Session) -> None:
        ensure_tables(db)

    # ---------------------------------------------------------------- entry pt

    def build_brief(
        self,
        db: Session,
        symbol: str,
        *,
        manual_option_snapshot_id: int | None = None,
        option_data_requested: bool = False,
        persist: bool = True,
        profile: StrategyProfile | None = None,
    ) -> BriefEvaluation:
        self.ensure_tables(db)
        clean = (symbol or "").strip().upper()
        if not clean:
            raise ValueError("symbol is required")

        has_manual_snapshot = manual_option_snapshot_id is not None
        if has_manual_snapshot:
            option_data_requested = True

        # Canonical decision (full detail) — not a bypass; this is THE service.
        decision = self.decision_service.evaluate_symbol(
            db=db,
            symbol=clean,
            manual_option_snapshot_id=manual_option_snapshot_id,
            option_data_requested=option_data_requested,
            persist=False,
            profile=profile,
        ).decision

        # Canonical action package.
        package = self.action_service.evaluate_symbol(
            db=db,
            symbol=clean,
            manual_option_snapshot_id=manual_option_snapshot_id,
            option_data_requested=option_data_requested,
            persist=False,
            profile=profile,
        ).package

        snapshot_record = self._load_manual_snapshot(db, manual_option_snapshot_id)
        missing_fields = list(snapshot_record.missing_fields) if snapshot_record else []

        inputs = BriefInputs(
            symbol=clean,
            snapshot_date=decision.snapshot_date or date.today(),
            final_action_label=package.final_action_label,
            suggested_action_summary=package.suggested_action_summary,
            priority_score=package.priority_score,
            confidence_score=package.confidence_score,
            lifecycle_state=package.lifecycle_state,
            instrument_scope=package.instrument_scope,
            stock_thesis=decision.stock_thesis.to_dict(),
            option_expression=decision.option_expression.to_dict(),
            option_contract_criteria=(
                package.option_contract_criteria.to_dict()
                if package.option_contract_criteria is not None
                else None
            ),
            has_manual_snapshot=has_manual_snapshot,
            manual_option_input_needed=bool(package.manual_option_input_needed),
            missing_fields=missing_fields,
            earnings=self._latest_earnings(db, clean),
            iv=self._latest_iv(db, clean),
            events=self._recent_events(db, clean),
            similar_cases=self._similar_cases(db, clean),
            decision_trace=list(decision.trace),
            confidence_breakdown=decision.confidence.breakdown.to_dict(),
            version_stamp=decision.version_stamp.to_dict(),
            profile_name=decision.profile_name,
            profile_version=decision.profile_version,
        )

        brief = build_ticker_brief(inputs)

        record: TickerBrief | None = None
        if persist:
            record = self._persist(db, brief)
        return BriefEvaluation(brief=brief, record=record)

    def list_briefs(
        self, db: Session, *, symbol: str | None = None, limit: int = 50
    ) -> list[TickerBrief]:
        self.ensure_tables(db)
        q = db.query(TickerBrief)
        if symbol is not None:
            q = q.filter(TickerBrief.symbol == symbol.strip().upper())
        return (
            q.order_by(TickerBrief.snapshot_date.desc(), TickerBrief.id.desc())
            .limit(limit)
            .all()
        )

    # ----------------------------------------------------------- gather helpers

    def _load_manual_snapshot(
        self, db: Session, snapshot_id: int | None
    ) -> ManualOptionSnapshotRecord | None:
        if snapshot_id is None:
            return None
        try:
            return self.manual_option_service.get_manual_snapshot_by_id(
                db=db, snapshot_id=snapshot_id
            )
        except Exception:
            return None

    def _latest_earnings(self, db: Session, symbol: str) -> dict[str, Any] | None:
        try:
            row: EarningsRiskSnapshot | None = (
                db.query(EarningsRiskSnapshot)
                .filter(EarningsRiskSnapshot.symbol == symbol)
                .order_by(
                    EarningsRiskSnapshot.snapshot_date.desc(),
                    EarningsRiskSnapshot.id.desc(),
                )
                .first()
            )
        except SQLAlchemyError:
            return None
        if row is None:
            return None
        return {
            "next_earnings_datetime_utc": row.next_earnings_datetime_utc.isoformat()
            if row.next_earnings_datetime_utc
            else None,
            "days_to_earnings": row.days_to_earnings,
            "earnings_within_window": bool(row.earnings_within_window),
            "earnings_before_expiration": row.earnings_before_expiration,
            "risk_label": row.risk_label,
        }

    def _latest_iv(self, db: Session, symbol: str) -> dict[str, Any] | None:
        try:
            row: IvRiskSnapshot | None = (
                db.query(IvRiskSnapshot)
                .filter(IvRiskSnapshot.symbol == symbol)
                .order_by(
                    IvRiskSnapshot.snapshot_date.desc(),
                    IvRiskSnapshot.id.desc(),
                )
                .first()
            )
        except SQLAlchemyError:
            return None
        if row is None:
            return None
        # Only report IV when the snapshot actually carries an IV value;
        # otherwise the section honestly reports IV as unavailable.
        if row.current_iv is None and row.iv_rank is None and row.iv_percentile is None:
            return None
        return {
            "current_iv": row.current_iv,
            "iv_rank": row.iv_rank,
            "iv_percentile": row.iv_percentile,
            "risk_label": row.risk_label,
        }

    def _recent_events(
        self, db: Session, symbol: str, limit: int = 5
    ) -> list[dict[str, Any]]:
        try:
            rows = (
                db.query(Event)
                .filter(Event.symbol == symbol)
                .order_by(Event.event_time.desc(), Event.id.desc())
                .limit(limit)
                .all()
            )
        except SQLAlchemyError:
            return []
        return [
            {
                "id": row.id,
                "event_type": row.event_type,
                "importance_level": row.importance_level,
                "headline": row.headline or row.source_title,
                "source_url": row.source_url,
                "event_time": row.event_time.isoformat() if row.event_time else None,
            }
            for row in rows
        ]

    def _similar_cases(self, db: Session, symbol: str) -> list[dict[str, Any]]:
        """Read stored case memory for the symbol when the table exists.

        Case memory (Phase 41) and vector memory (Phase 42) populate this. The
        brief degrades gracefully (empty list) when no cases are stored yet, so
        the memory section reports absence honestly rather than inventing data.
        """
        try:
            from app.memory.case_memory_models import CaseMemory  # local import

            rows = (
                db.query(CaseMemory)
                .filter(CaseMemory.symbol == symbol)
                .order_by(CaseMemory.created_at.desc())
                .limit(5)
                .all()
            )
        except Exception:
            return []
        return [
            {
                "id": row.id,
                "case_type": row.case_type,
                "outcome_type": row.outcome_type,
                "lesson_summary": row.lesson_summary,
                "option_data_available": row.option_data_available,
            }
            for row in rows
        ]

    # ------------------------------------------------------------ persistence

    def _persist(self, db: Session, brief: TickerBriefResult) -> TickerBrief:
        existing = (
            db.query(TickerBrief)
            .filter(TickerBrief.symbol == brief.symbol)
            .filter(TickerBrief.snapshot_date == brief.snapshot_date)
            .one_or_none()
        )
        values = {
            "final_action_label": brief.final_action_label,
            "instrument_scope": brief.instrument_scope,
            "lifecycle_state": brief.lifecycle_state,
            "option_expression_status": brief.option_expression_status,
            "priority_score": brief.priority_score,
            "confidence_score": brief.confidence_score,
            "sections_json": list(brief.sections),
            "version_stamp_json": dict(brief.version_stamp),
            "profile_name": brief.profile_name,
            "profile_version": brief.profile_version,
        }
        if existing is None:
            row = TickerBrief(
                symbol=brief.symbol,
                snapshot_date=brief.snapshot_date,
                **values,
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            return row
        for key, value in values.items():
            setattr(existing, key, value)
        db.commit()
        db.refresh(existing)
        return existing


__all__ = ["BriefEvaluation", "TickerBriefService"]
