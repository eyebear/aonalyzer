"""Phase 41, steps 41.2-41.9 — case memory builder + summarizer.

Converts actual recorded outcomes into reusable cases without inventing
conclusions. It reads the Phase 38-40 outcome tables (signal, rejection/freeze,
override), classifies the case type — including the key
STOCK_RIGHT_OPTION_WRONG / STOCK_RIGHT_OPTION_MISSING / MANUAL_OPTION_ANALYSIS
types — writes a plain-language lesson, and marks each source row fed so a case
is created once.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.common.service_utils import ensure_tables
from app.learning.rejection_outcome_models import (
    SOURCE_DO_NOT_TOUCH as RO_SOURCE_DNT,
)
from app.learning.rejection_outcome_models import (
    WOULD_OPTION_FALSE,
)
from app.learning.rejection_outcome_service import RejectionOutcomeService
from app.learning.signal_outcome_models import OPTION_OUTCOME_ESTIMATED
from app.learning.signal_outcome_service import SignalOutcomeService
from app.memory.case_memory_models import (
    CASE_DO_NOT_TOUCH,
    CASE_MANUAL_OPTION_ANALYSIS,
    CASE_OVERRIDE,
    CASE_REJECTION_OUTCOME,
    CASE_SIGNAL_OUTCOME,
    CASE_STOCK_RIGHT_OPTION_MISSING,
    CASE_STOCK_RIGHT_OPTION_WRONG,
    SOURCE_OVERRIDE,
    SOURCE_REJECTION,
    SOURCE_SIGNAL,
    CaseMemory,
)
from app.user_actions.user_action_service import UserActionService


@dataclass
class CaseBuildResult:
    cases_created: int = 0
    cases_skipped: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "cases_created": self.cases_created,
            "cases_skipped": self.cases_skipped,
        }


class CaseMemoryService:
    def __init__(
        self,
        signal_service: SignalOutcomeService | None = None,
        rejection_service: RejectionOutcomeService | None = None,
        user_action_service: UserActionService | None = None,
    ) -> None:
        self.signal_service = signal_service or SignalOutcomeService()
        self.rejection_service = rejection_service or RejectionOutcomeService()
        self.user_action_service = user_action_service or UserActionService()

    def ensure_tables(self, db: Session) -> None:
        ensure_tables(db)

    # ----------------------------------------------------------------- build

    def build_cases(self, db: Session, *, limit: int = 200) -> CaseBuildResult:
        self.ensure_tables(db)
        result = CaseBuildResult()

        self._build_from_signals(db, result, limit)
        self._build_from_rejections(db, result, limit)
        self._build_from_overrides(db, result, limit)

        db.commit()
        return result

    def _build_from_signals(
        self, db: Session, result: CaseBuildResult, limit: int
    ) -> None:
        rows = self.signal_service.pending_for_memory(db, limit=limit)
        fed_ids: list[int] = []
        for row in rows:
            # One case per signal: prefer the longest-horizon evaluation by
            # keying on (symbol, signal_date). Use this row's data.
            case_type, outcome_type = self._classify_signal(row)
            option_available = row.option_outcome_status == OPTION_OUTCOME_ESTIMATED
            lesson = self._summarize_signal(row, case_type)
            created = self._upsert_case(
                db,
                symbol=row.symbol,
                case_type=case_type,
                source_type=SOURCE_SIGNAL,
                source_id=row.id,
                snapshot_date=row.signal_date,
                outcome_type=outcome_type,
                option_data_available=option_available,
                lesson=lesson,
                context={
                    "horizon_days": row.horizon_days,
                    "stock_return_pct": row.stock_return_pct,
                    "target_hit": row.target_hit,
                    "stop_hit": row.stop_hit,
                    "option_outcome_status": row.option_outcome_status,
                    "option_return_pct": row.option_return_pct,
                },
            )
            result.cases_created += int(created)
            result.cases_skipped += int(not created)
            fed_ids.append(row.id)
        self.signal_service.mark_fed_to_memory(db, fed_ids)

    def _build_from_rejections(
        self, db: Session, result: CaseBuildResult, limit: int
    ) -> None:
        rows = self.rejection_service.pending_for_memory(db, limit=limit)
        fed_ids: list[int] = []
        for row in rows:
            is_dnt = row.source_type == RO_SOURCE_DNT
            case_type = CASE_DO_NOT_TOUCH if is_dnt else CASE_REJECTION_OUTCOME
            outcome_type = (
                "TOO_STRICT"
                if row.is_too_strict
                else ("CORRECT" if row.was_rejection_correct else "UNKNOWN")
            )
            lesson = self._summarize_rejection(row, is_dnt)
            created = self._upsert_case(
                db,
                symbol=row.symbol,
                case_type=case_type,
                source_type=SOURCE_REJECTION,
                source_id=row.id,
                snapshot_date=row.snapshot_date,
                outcome_type=outcome_type,
                option_data_available=bool(row.option_data_available),
                lesson=lesson,
                context={
                    "source_type": row.source_type,
                    "category": row.category,
                    "stock_return_pct": row.stock_return_pct,
                    "would_option_have_worked": row.would_option_have_worked,
                },
            )
            result.cases_created += int(created)
            result.cases_skipped += int(not created)
            fed_ids.append(row.id)
        self._mark_rejection_fed(db, fed_ids)

    def _build_from_overrides(
        self, db: Session, result: CaseBuildResult, limit: int
    ) -> None:
        rows = self.user_action_service.pending_for_memory(db, limit=limit)
        fed_ids: list[int] = []
        for row in rows:
            lesson = (
                f"{row.override_type}: {row.detail or ''} "
                f"({row.outcome_classification})."
            )
            created = self._upsert_case(
                db,
                symbol=row.symbol,
                case_type=CASE_OVERRIDE,
                source_type=SOURCE_OVERRIDE,
                source_id=row.id,
                snapshot_date=None,
                outcome_type=row.outcome_classification,
                option_data_available=False,
                lesson=lesson,
                context={
                    "override_type": row.override_type,
                    "stock_return_pct": row.stock_return_pct,
                    "is_missed_opportunity": row.is_missed_opportunity,
                    "is_avoided_correctly": row.is_avoided_correctly,
                },
            )
            result.cases_created += int(created)
            result.cases_skipped += int(not created)
            fed_ids.append(row.id)
        self._mark_override_fed(db, fed_ids)

    # --------------------------------------------------------------- classify

    def _classify_signal(self, row: Any) -> tuple[str, str]:
        target_hit = bool(row.target_hit)
        stop_hit = bool(row.stop_hit)
        option_estimated = row.option_outcome_status == OPTION_OUTCOME_ESTIMATED

        if target_hit and option_estimated and (row.option_return_pct or 0) < 0:
            # Stock thesis was right but the option expression lost money.
            return CASE_STOCK_RIGHT_OPTION_WRONG, "STOCK_RIGHT_OPTION_WRONG"
        if target_hit and not option_estimated:
            # Stock thesis was right but option data was missing/unevaluated.
            return CASE_STOCK_RIGHT_OPTION_MISSING, "STOCK_RIGHT_OPTION_MISSING"
        if option_estimated:
            return CASE_MANUAL_OPTION_ANALYSIS, (
                "TARGET_HIT" if target_hit else ("STOP_HIT" if stop_hit else "FLAT")
            )
        outcome = "TARGET_HIT" if target_hit else ("STOP_HIT" if stop_hit else "FLAT")
        return CASE_SIGNAL_OUTCOME, outcome

    # -------------------------------------------------------------- summarize

    def _summarize_signal(self, row: Any, case_type: str) -> str:
        ret = row.stock_return_pct
        ret_str = f"{ret:+.1f}%" if ret is not None else "n/a"
        if case_type == CASE_STOCK_RIGHT_OPTION_WRONG:
            return (
                f"{row.symbol}: stock hit target ({ret_str} at {row.horizon_days}d) "
                "but the pasted option lost value — option expression was the weak link."
            )
        if case_type == CASE_STOCK_RIGHT_OPTION_MISSING:
            return (
                f"{row.symbol}: stock thesis was right ({ret_str} at {row.horizon_days}d) "
                "but no option data was available to evaluate an option expression."
            )
        return (
            f"{row.symbol}: {row.horizon_days}-day stock return {ret_str}; "
            f"target_hit={row.target_hit}, stop_hit={row.stop_hit}."
        )

    def _summarize_rejection(self, row: Any, is_dnt: bool) -> str:
        what = "freeze" if is_dnt else "rejection"
        ret = row.stock_return_pct
        ret_str = f"{ret:+.1f}%" if ret is not None else "n/a"
        verdict = (
            "was too strict" if row.is_too_strict else "looks correct"
        )
        opt = ""
        if row.would_option_have_worked == WOULD_OPTION_FALSE:
            opt = " The option would not have worked either."
        return (
            f"{row.symbol}: {what} {verdict} — {row.horizon_days}-day stock return "
            f"{ret_str}.{opt}"
        )

    # ------------------------------------------------------------- persistence

    def _upsert_case(
        self,
        db: Session,
        *,
        symbol: str,
        case_type: str,
        source_type: str,
        source_id: int | None,
        snapshot_date: Any,
        outcome_type: str | None,
        option_data_available: bool,
        lesson: str,
        context: dict[str, Any],
    ) -> bool:
        existing = (
            db.query(CaseMemory)
            .filter(CaseMemory.source_type == source_type)
            .filter(CaseMemory.source_id == source_id)
            .one_or_none()
        )
        if existing is not None:
            existing.case_type = case_type
            existing.outcome_type = outcome_type
            existing.option_data_available = option_data_available
            existing.lesson_summary = lesson
            existing.decision_context_json = context
            return False
        db.add(
            CaseMemory(
                symbol=symbol,
                case_type=case_type,
                source_type=source_type,
                source_id=source_id,
                snapshot_date=snapshot_date,
                outcome_type=outcome_type,
                option_data_available=option_data_available,
                lesson_summary=lesson,
                decision_context_json=context,
            )
        )
        return True

    def _mark_rejection_fed(self, db: Session, ids: list[int]) -> None:
        if not ids:
            return
        from app.learning.rejection_outcome_models import RejectionOutcome

        for row in db.query(RejectionOutcome).filter(RejectionOutcome.id.in_(ids)).all():
            row.fed_to_memory = True

    def _mark_override_fed(self, db: Session, ids: list[int]) -> None:
        if not ids:
            return
        from app.user_actions.user_action_models import OverrideOutcome

        for row in db.query(OverrideOutcome).filter(OverrideOutcome.id.in_(ids)).all():
            row.fed_to_memory = True

    # ------------------------------------------------------------- lookups

    def list_cases(
        self,
        db: Session,
        *,
        symbol: str | None = None,
        case_type: str | None = None,
        limit: int = 200,
    ) -> list[CaseMemory]:
        self.ensure_tables(db)
        q = db.query(CaseMemory)
        if symbol is not None:
            q = q.filter(CaseMemory.symbol == symbol.strip().upper())
        if case_type is not None:
            q = q.filter(CaseMemory.case_type == case_type.upper())
        return q.order_by(CaseMemory.created_at.desc()).limit(limit).all()


__all__ = ["CaseBuildResult", "CaseMemoryService"]
