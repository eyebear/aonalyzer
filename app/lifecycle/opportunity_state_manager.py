"""Phase 25, step 25.3 — Opportunity state manager.

Owns mutations on ``opportunity_lifecycle``. Idempotent updates: if the
current_state matches the target, the manager only refreshes
``last_evaluated_at``. Real state changes also log a transition row via
``LifecycleHistoryWriter``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.common.service_utils import ensure_tables
from app.lifecycle.lifecycle_history_writer import LifecycleHistoryWriter
from app.lifecycle.lifecycle_models import OpportunityLifecycle
from app.lifecycle.lifecycle_states import (
    REVIEW_DISMISSED,
    REVIEW_REVIEWED,
    REVIEW_UNREVIEWED,
)
from app.lifecycle.state_transition_engine import (
    KIND_REACTIVATION,
    TransitionPlan,
)


@dataclass
class StateUpdateResult:
    lifecycle: OpportunityLifecycle
    plan: TransitionPlan
    transition_id: int | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "lifecycle_id": self.lifecycle.id,
            "plan": self.plan.to_dict(),
            "transition_id": self.transition_id,
        }


class OpportunityStateManager:
    def __init__(
        self,
        history_writer: LifecycleHistoryWriter | None = None,
    ) -> None:
        self.history_writer = history_writer or LifecycleHistoryWriter()

    def ensure_tables(self, db: Session) -> None:
        ensure_tables(db)

    # --------------------------------------------------------------- lookups

    def get(self, db: Session, symbol: str) -> OpportunityLifecycle | None:
        clean = (symbol or "").strip().upper()
        if not clean:
            return None
        try:
            return (
                db.query(OpportunityLifecycle)
                .filter(OpportunityLifecycle.symbol == clean)
                .one_or_none()
            )
        except SQLAlchemyError:
            return None

    def list_active(self, db: Session) -> list[OpportunityLifecycle]:
        return (
            db.query(OpportunityLifecycle)
            .order_by(
                OpportunityLifecycle.last_transition_at.desc(),
                OpportunityLifecycle.id.desc(),
            )
            .all()
        )

    # --------------------------------------------------------------- mutate

    def apply_transition(
        self,
        db: Session,
        *,
        symbol: str,
        plan: TransitionPlan,
        reason_label: str,
        reason_summary: str,
        triggered_by: str,
        source_phase: str,
        final_action_label: str | None = None,
        context: dict[str, Any] | None = None,
        profile_name: str | None = None,
        profile_version: str | None = None,
        now: datetime | None = None,
    ) -> StateUpdateResult:
        self.ensure_tables(db)
        clean = (symbol or "").strip().upper()
        if not clean:
            raise ValueError("symbol is required")

        now = now or datetime.now(timezone.utc)

        existing = (
            db.query(OpportunityLifecycle)
            .filter(OpportunityLifecycle.symbol == clean)
            .one_or_none()
        )

        if existing is None:
            row = OpportunityLifecycle(
                symbol=clean,
                current_state=plan.to_state,
                previous_state=None,
                last_transition_at=now,
                last_evaluated_at=now,
                final_action_label=final_action_label,
                user_review_status=REVIEW_UNREVIEWED,
                profile_name=profile_name,
                profile_version=profile_version,
                context_json=dict(context or {}),
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            transition = self.history_writer.append(
                db=db,
                symbol=clean,
                from_state=None,
                to_state=plan.to_state,
                reason_label=reason_label,
                reason_summary=reason_summary,
                triggered_by=triggered_by,
                source_phase=source_phase,
                final_action_label=final_action_label,
                context=context,
                profile_name=profile_name,
                profile_version=profile_version,
            )
            return StateUpdateResult(
                lifecycle=row, plan=plan, transition_id=transition.id
            )

        # No-change refresh.
        if not plan.is_change:
            existing.last_evaluated_at = now
            existing.final_action_label = final_action_label or existing.final_action_label
            existing.context_json = dict(context or existing.context_json or {})
            db.commit()
            db.refresh(existing)
            return StateUpdateResult(
                lifecycle=existing, plan=plan, transition_id=None
            )

        # Real transition.
        existing.previous_state = existing.current_state
        existing.current_state = plan.to_state
        existing.last_transition_at = now
        existing.last_evaluated_at = now
        existing.final_action_label = final_action_label or existing.final_action_label
        existing.context_json = dict(context or existing.context_json or {})
        existing.profile_name = profile_name or existing.profile_name
        existing.profile_version = profile_version or existing.profile_version
        # Reset review-status on a real transition so the user sees the new
        # state again; preserve REVIEWED status only on a no-op refresh.
        existing.user_review_status = REVIEW_UNREVIEWED
        existing.user_reviewed_at = None
        if plan.kind == KIND_REACTIVATION:
            existing.last_reactivation_at = now

        db.commit()
        db.refresh(existing)
        transition = self.history_writer.append(
            db=db,
            symbol=clean,
            from_state=plan.from_state,
            to_state=plan.to_state,
            reason_label=reason_label,
            reason_summary=reason_summary,
            triggered_by=triggered_by,
            source_phase=source_phase,
            final_action_label=final_action_label,
            context=context,
            profile_name=profile_name,
            profile_version=profile_version,
        )
        return StateUpdateResult(
            lifecycle=existing, plan=plan, transition_id=transition.id
        )

    # ------------------------------------------------------------- review

    def mark_reviewed(
        self,
        db: Session,
        symbol: str,
        *,
        review_status: str = REVIEW_REVIEWED,
        now: datetime | None = None,
    ) -> OpportunityLifecycle | None:
        if review_status not in {REVIEW_REVIEWED, REVIEW_DISMISSED, REVIEW_UNREVIEWED}:
            raise ValueError(f"unknown review status '{review_status}'")
        existing = self.get(db, symbol)
        if existing is None:
            return None
        now = now or datetime.now(timezone.utc)
        existing.user_review_status = review_status
        existing.user_reviewed_at = (
            now if review_status != REVIEW_UNREVIEWED else None
        )
        db.commit()
        db.refresh(existing)
        return existing


__all__ = ["OpportunityStateManager", "StateUpdateResult"]
