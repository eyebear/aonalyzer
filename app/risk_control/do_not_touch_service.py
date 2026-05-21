"""Phase 24 — DB-facing orchestrator for the Do-Not-Touch risk control layer.

Pulls together the Phase 23 rejection classification + the Phase 21
decision, runs the Phase 24 classifier, applies the freeze (or no-op)
via the manager, and surfaces the explainer. Manual freeze / release
endpoints delegate directly to the manager.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.common.service_utils import ensure_tables
from app.core.config import AppSettings, get_settings
from app.profiles.profile_manager import profile_manager
from app.profiles.profile_models import StrategyProfile
from app.rejection.rejection_classifier import classify_rejection
from app.rejection.rejection_service import RejectionService
from app.risk_control.do_not_touch_categories import (
    FREEZE_CATEGORY_MANUAL,
    SEVERITY_HARD_FREEZE,
    SEVERITY_SOFT_FREEZE,
    SOURCE_PHASE_CLASSIFIER,
    SOURCE_PHASE_MANUAL,
    TRIGGER_AUTOMATIC,
    TRIGGER_USER,
)
from app.risk_control.do_not_touch_classifier import (
    DECISION_FREEZE,
    FreezeRecommendation,
    classify_do_not_touch,
)
from app.risk_control.do_not_touch_explainer import (
    DoNotTouchExplanation,
    explain_freeze,
)
from app.risk_control.do_not_touch_models import DoNotTouchItem
from app.risk_control.release_condition_builder import (
    ReleaseCondition,
    build_release_condition,
)
from app.risk_control.temporary_freeze_manager import (
    FreezeOperationResult,
    TemporaryFreezeManager,
)


@dataclass
class DoNotTouchEvaluation:
    recommendation: FreezeRecommendation
    operation: FreezeOperationResult
    release_condition: ReleaseCondition | None
    explanation: DoNotTouchExplanation | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "recommendation": self.recommendation.to_dict(),
            "operation": self.operation.to_dict(),
            "release_condition": (
                self.release_condition.to_dict()
                if self.release_condition is not None
                else None
            ),
            "explanation": (
                self.explanation.to_dict()
                if self.explanation is not None
                else None
            ),
        }


class DoNotTouchService:
    def __init__(
        self,
        settings: AppSettings | None = None,
        rejection_service: RejectionService | None = None,
        freeze_manager: TemporaryFreezeManager | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.rejection_service = rejection_service or RejectionService(
            settings=self.settings
        )
        self.freeze_manager = freeze_manager or TemporaryFreezeManager()

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
        persist: bool = True,
        profile: StrategyProfile | None = None,
        now: datetime | None = None,
    ) -> DoNotTouchEvaluation:
        self.ensure_tables(db)
        clean = (symbol or "").strip().upper()
        if not clean:
            raise ValueError("symbol is required")

        active_profile = profile or self._safe_profile()

        # Reuse the Phase 23 rejection service to get the full upstream
        # chain (Phase 19/20/21/22/23). We do not persist from here.
        rejection_eval = self.rejection_service.evaluate_symbol(
            db=db,
            symbol=clean,
            manual_option_snapshot_id=manual_option_snapshot_id,
            option_data_requested=option_data_requested,
            persist=False,
            profile=active_profile,
        )
        # Reconstruct the FinalDecision via the rejection service's
        # action service -> decision service chain so the classifier sees
        # the same Phase 21 outputs.
        decision = self.rejection_service.action_service.decision_service.evaluate_symbol(
            db=db,
            symbol=clean,
            manual_option_snapshot_id=manual_option_snapshot_id,
            option_data_requested=option_data_requested,
            persist=False,
            profile=active_profile,
        ).decision

        # Phase 23 classification (already inside rejection_eval, but recompute
        # to avoid coupling to its internal shape).
        rejection = classify_rejection(
            decision,
            profile_minimum_risk_reward=(
                float(active_profile.minimum_risk_reward)
                if active_profile is not None
                else None
            ),
        )

        recommendation = classify_do_not_touch(
            decision=decision,
            rejection=rejection,
            db=db,
            symbol=clean,
        )

        release_condition: ReleaseCondition | None = None
        explanation: DoNotTouchExplanation | None = None
        operation = FreezeOperationResult(item=None, event_type=None)

        if recommendation.decision == DECISION_FREEZE and persist:
            earnings_dt = _earnings_dt_from_decision(decision)
            release_condition = build_release_condition(
                category=recommendation.category or "",
                now=now,
                earnings_datetime_utc=earnings_dt,
            )
            operation = self.freeze_manager.freeze(
                db=db,
                symbol=clean,
                category=recommendation.category or "",
                severity=recommendation.severity or SEVERITY_SOFT_FREEZE,
                release_condition=release_condition,
                reason_summary=recommendation.reason_summary,
                triggered_by=recommendation.triggered_by,
                source_phase=recommendation.source_phase,
                context=recommendation.context,
                profile_name=active_profile.profile_name if active_profile else None,
                profile_version=(
                    active_profile.profile_version if active_profile else None
                ),
            )
            explanation = explain_freeze(
                category=recommendation.category or "",
                severity=recommendation.severity or SEVERITY_SOFT_FREEZE,
                reason_summary=recommendation.reason_summary,
            )

        elif recommendation.decision == DECISION_FREEZE and not persist:
            # Pure dry-run -- produce explanation + release condition but
            # do not mutate state.
            earnings_dt = _earnings_dt_from_decision(decision)
            release_condition = build_release_condition(
                category=recommendation.category or "",
                now=now,
                earnings_datetime_utc=earnings_dt,
            )
            explanation = explain_freeze(
                category=recommendation.category or "",
                severity=recommendation.severity or SEVERITY_SOFT_FREEZE,
                reason_summary=recommendation.reason_summary,
            )

        # Keep rejection_eval reachable in case future phases want a single
        # combined audit pass.
        _ = rejection_eval

        return DoNotTouchEvaluation(
            recommendation=recommendation,
            operation=operation,
            release_condition=release_condition,
            explanation=explanation,
        )

    # ---------------------------------------------------------------- manual

    def manual_freeze(
        self,
        db: Session,
        *,
        symbol: str,
        reason: str,
        severity: str = SEVERITY_HARD_FREEZE,
        expires_at: datetime | None = None,
        profile: StrategyProfile | None = None,
    ) -> DoNotTouchEvaluation:
        self.ensure_tables(db)
        active_profile = profile or self._safe_profile()

        release_condition = build_release_condition(
            category=FREEZE_CATEGORY_MANUAL,
            override_expires_at=expires_at,
        )
        operation = self.freeze_manager.freeze(
            db=db,
            symbol=symbol,
            category=FREEZE_CATEGORY_MANUAL,
            severity=severity,
            release_condition=release_condition,
            reason_summary=reason or "Manual freeze applied by user.",
            triggered_by=TRIGGER_USER,
            source_phase=SOURCE_PHASE_MANUAL,
            context={"manual": True},
            profile_name=active_profile.profile_name if active_profile else None,
            profile_version=(
                active_profile.profile_version if active_profile else None
            ),
        )
        explanation = explain_freeze(
            category=FREEZE_CATEGORY_MANUAL,
            severity=severity,
            reason_summary=reason,
        )
        recommendation = FreezeRecommendation(
            decision=DECISION_FREEZE,
            category=FREEZE_CATEGORY_MANUAL,
            severity=severity,
            reason_summary=reason or "Manual freeze applied by user.",
            source_phase=SOURCE_PHASE_MANUAL,
            triggered_by=TRIGGER_USER,
        )
        return DoNotTouchEvaluation(
            recommendation=recommendation,
            operation=operation,
            release_condition=release_condition,
            explanation=explanation,
        )

    def manual_release(
        self,
        db: Session,
        *,
        symbol: str,
        reason: str,
    ) -> FreezeOperationResult:
        self.ensure_tables(db)
        return self.freeze_manager.release(
            db=db,
            symbol=symbol,
            release_reason=reason or "Manual release by user.",
            triggered_by=TRIGGER_USER,
            source_phase=SOURCE_PHASE_MANUAL,
        )

    # ---------------------------------------------------------------- lookups

    def list_active(self, db: Session) -> list[DoNotTouchItem]:
        self.ensure_tables(db)
        return (
            db.query(DoNotTouchItem)
            .order_by(DoNotTouchItem.frozen_at.desc(), DoNotTouchItem.id.desc())
            .all()
        )

    def get_active(self, db: Session, symbol: str) -> DoNotTouchItem | None:
        return self.freeze_manager.get_active(db, symbol)

    def is_frozen(self, db: Session, symbol: str) -> bool:
        return self.freeze_manager.is_frozen(db, symbol)

    # ---------------------------------------------------------------- helpers

    def _safe_profile(self) -> StrategyProfile | None:
        try:
            return profile_manager.get_active_profile()
        except Exception:
            return None


def _earnings_dt_from_decision(decision) -> datetime | None:
    """Pull the earnings datetime out of the decision's hard-filter
    earnings context if available. Returns ``None`` if unknown so the
    release-condition builder falls back to the default window."""
    try:
        for o in decision.hard_filter_decision.outcomes:
            if o.name == "earnings_risk" and o.detail and "earnings" in o.detail.lower():
                return None  # detail string only -- no datetime here
    except Exception:
        pass
    return None


__all__ = ["DoNotTouchEvaluation", "DoNotTouchService"]
