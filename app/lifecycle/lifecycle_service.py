"""Phase 25 — DB-facing orchestrator for the opportunity lifecycle layer.

Pulls the Phase 22 action package, plans the transition via
``state_transition_engine``, builds the reason via
``state_reason_builder``, and applies it via
``OpportunityStateManager``. Manual review goes through
``UserReviewStateTracker``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.action.action_service import ActionEvaluation, ActionSuggestionService
from app.common.service_utils import ensure_tables
from app.core.config import AppSettings, get_settings
from app.lifecycle.lifecycle_models import (
    OpportunityLifecycle,
    OpportunityStateTransition,
)
from app.lifecycle.lifecycle_states import (
    SOURCE_PHASE_PHASE22,
    SOURCE_PHASE_REACTIVATION,
    TRIGGER_SYSTEM_EVALUATION,
    TRIGGER_SYSTEM_REACTIVATION,
)
from app.lifecycle.opportunity_state_manager import (
    OpportunityStateManager,
    StateUpdateResult,
)
from app.lifecycle.reactivation_engine import ReactivationEngine
from app.lifecycle.state_reason_builder import build_transition_reason
from app.lifecycle.state_transition_engine import (
    KIND_REACTIVATION,
    plan_transition,
)
from app.lifecycle.user_review_state_tracker import UserReviewStateTracker
from app.profiles.profile_manager import profile_manager
from app.profiles.profile_models import StrategyProfile


@dataclass
class LifecycleEvaluation:
    lifecycle: OpportunityLifecycle
    update: StateUpdateResult

    def to_dict(self) -> dict[str, Any]:
        return {"lifecycle_id": self.lifecycle.id, "update": self.update.to_dict()}


class LifecycleService:
    def __init__(
        self,
        settings: AppSettings | None = None,
        action_service: ActionSuggestionService | None = None,
        state_manager: OpportunityStateManager | None = None,
        review_tracker: UserReviewStateTracker | None = None,
        reactivation_engine: ReactivationEngine | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.action_service = action_service or ActionSuggestionService(
            settings=self.settings
        )
        self.state_manager = state_manager or OpportunityStateManager()
        self.review_tracker = review_tracker or UserReviewStateTracker(
            manager=self.state_manager,
        )
        self.reactivation_engine = reactivation_engine or ReactivationEngine()

    def ensure_tables(self, db: Session) -> None:
        ensure_tables(db)

    # ---------------------------------------------------------------- entry pt

    def evaluate_symbol(
        self,
        db: Session,
        symbol: str,
        *,
        manual_option_snapshot_id: int | None = None,
        option_data_requested: bool = False,
        profile: StrategyProfile | None = None,
        now: datetime | None = None,
    ) -> LifecycleEvaluation:
        self.ensure_tables(db)
        clean = (symbol or "").strip().upper()
        if not clean:
            raise ValueError("symbol is required")

        active_profile = profile or self._safe_profile()

        action_eval: ActionEvaluation = self.action_service.evaluate_symbol(
            db=db,
            symbol=clean,
            manual_option_snapshot_id=manual_option_snapshot_id,
            option_data_requested=option_data_requested,
            persist=False,
            profile=active_profile,
        )
        package = action_eval.package

        existing = self.state_manager.get(db, clean)
        plan = plan_transition(
            current_state=existing.current_state if existing is not None else None,
            target_state_phase22=package.lifecycle_state,
        )
        reason = build_transition_reason(
            plan,
            final_action_label=package.final_action_label,
        )
        triggered_by = (
            TRIGGER_SYSTEM_REACTIVATION
            if plan.kind == KIND_REACTIVATION
            else TRIGGER_SYSTEM_EVALUATION
        )

        update = self.state_manager.apply_transition(
            db=db,
            symbol=clean,
            plan=plan,
            reason_label=reason.label,
            reason_summary=reason.summary,
            triggered_by=triggered_by,
            source_phase=SOURCE_PHASE_PHASE22,
            final_action_label=package.final_action_label,
            context={
                "phase22_lifecycle_state": package.lifecycle_state,
                "priority_score": package.priority_score,
                "confidence_score": package.confidence_score,
            },
            profile_name=package.profile_name,
            profile_version=package.profile_version,
            now=now,
        )

        return LifecycleEvaluation(lifecycle=update.lifecycle, update=update)

    # ------------------------------------------------------------ batch

    def evaluate_many(
        self,
        db: Session,
        symbols: list[str],
        *,
        option_data_requested: bool = False,
        profile: StrategyProfile | None = None,
    ) -> list[LifecycleEvaluation]:
        results: list[LifecycleEvaluation] = []
        for symbol in symbols:
            try:
                results.append(
                    self.evaluate_symbol(
                        db=db,
                        symbol=symbol,
                        option_data_requested=option_data_requested,
                        profile=profile,
                    )
                )
            except Exception:
                # Skip symbols whose Phase 22 chain fails; lifecycle is best-
                # effort and never raises out of a batch.
                continue
        return results

    # ------------------------------------------------------------ lookups

    def list_active(self, db: Session) -> list[OpportunityLifecycle]:
        self.ensure_tables(db)
        return self.state_manager.list_active(db)

    def get(self, db: Session, symbol: str) -> OpportunityLifecycle | None:
        self.ensure_tables(db)
        return self.state_manager.get(db, symbol)

    def get_history(
        self,
        db: Session,
        symbol: str,
        *,
        limit: int = 100,
    ) -> list[OpportunityStateTransition]:
        self.ensure_tables(db)
        clean = (symbol or "").strip().upper()
        if not clean:
            return []
        return (
            db.query(OpportunityStateTransition)
            .filter(OpportunityStateTransition.symbol == clean)
            .order_by(
                OpportunityStateTransition.created_at.desc(),
                OpportunityStateTransition.id.desc(),
            )
            .limit(limit)
            .all()
        )

    # ------------------------------------------------------------ review

    def mark_review(
        self,
        db: Session,
        symbol: str,
        *,
        review_status: str,
        notes: str | None = None,
    ) -> dict[str, Any]:
        self.ensure_tables(db)
        return self.review_tracker.mark(
            db=db, symbol=symbol, review_status=review_status, notes=notes
        )

    # ------------------------------------------------------------ reactivation

    def detect_reactivations(
        self,
        db: Session,
        *,
        symbols: list[str] | None = None,
        option_data_requested: bool = False,
        profile: StrategyProfile | None = None,
    ) -> list[LifecycleEvaluation]:
        """Re-run Phase 22 for terminal-state symbols and reactivate any
        that move into an active state."""
        self.ensure_tables(db)
        active_profile = profile or self._safe_profile()

        # Build the {symbol: phase22 lifecycle state} map for terminal-state
        # symbols only.
        from app.lifecycle.lifecycle_states import TERMINAL_STATES

        terminal_symbols = [
            row.symbol
            for row in db.query(OpportunityLifecycle)
            .filter(
                OpportunityLifecycle.current_state.in_(list(TERMINAL_STATES))
            )
            .all()
        ]
        if symbols is not None:
            terminal_symbols = [s for s in terminal_symbols if s in {s.upper() for s in symbols}]

        latest_actions: dict[str, str] = {}
        for symbol in terminal_symbols:
            try:
                pkg = self.action_service.evaluate_symbol(
                    db=db,
                    symbol=symbol,
                    option_data_requested=option_data_requested,
                    persist=False,
                    profile=active_profile,
                ).package
                latest_actions[symbol] = pkg.lifecycle_state
            except Exception:
                continue

        detected = self.reactivation_engine.detect(
            db=db, latest_actions=latest_actions
        )

        results: list[LifecycleEvaluation] = []
        for candidate in detected.candidates:
            results.append(
                self.evaluate_symbol(
                    db=db,
                    symbol=candidate.symbol,
                    option_data_requested=option_data_requested,
                    profile=active_profile,
                )
            )
        return results

    # ------------------------------------------------------------ helpers

    def _safe_profile(self) -> StrategyProfile | None:
        try:
            return profile_manager.get_active_profile()
        except Exception:
            return None


__all__ = ["LifecycleEvaluation", "LifecycleService"]
