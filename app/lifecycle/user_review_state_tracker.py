"""Phase 25, step 25.8 — User review state tracker.

Thin wrapper around ``OpportunityStateManager.mark_reviewed`` that
records the user-review event as a transition row (event-only --
``from_state == to_state``) so the audit trail captures the user's
interaction history. The lifecycle row itself is also updated.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.lifecycle.lifecycle_history_writer import LifecycleHistoryWriter
from app.lifecycle.lifecycle_models import OpportunityLifecycle
from app.lifecycle.lifecycle_states import (
    REVIEW_DISMISSED,
    REVIEW_REVIEWED,
    REVIEW_UNREVIEWED,
    SOURCE_PHASE_USER,
    TRIGGER_USER,
)
from app.lifecycle.opportunity_state_manager import OpportunityStateManager


class UserReviewStateTracker:
    def __init__(
        self,
        manager: OpportunityStateManager | None = None,
        history_writer: LifecycleHistoryWriter | None = None,
    ) -> None:
        self.manager = manager or OpportunityStateManager()
        self.history_writer = history_writer or LifecycleHistoryWriter()

    def mark(
        self,
        db: Session,
        *,
        symbol: str,
        review_status: str,
        notes: str | None = None,
    ) -> dict[str, Any]:
        if review_status not in (
            REVIEW_REVIEWED,
            REVIEW_DISMISSED,
            REVIEW_UNREVIEWED,
        ):
            raise ValueError(f"unknown review status '{review_status}'")

        lifecycle: OpportunityLifecycle | None = self.manager.mark_reviewed(
            db=db, symbol=symbol, review_status=review_status
        )
        if lifecycle is None:
            return {"updated": False, "transition_id": None, "lifecycle": None}

        now = datetime.now(timezone.utc)
        summary = (
            f"User marked {symbol.upper()} as {review_status} at {now.isoformat()}"
            + (f" — {notes}" if notes else ".")
        )
        transition = self.history_writer.append(
            db=db,
            symbol=symbol,
            from_state=lifecycle.current_state,
            to_state=lifecycle.current_state,
            reason_label=f"USER_{review_status}",
            reason_summary=summary,
            triggered_by=TRIGGER_USER,
            source_phase=SOURCE_PHASE_USER,
            final_action_label=lifecycle.final_action_label,
            context={"review_status": review_status, "notes": notes},
            profile_name=lifecycle.profile_name,
            profile_version=lifecycle.profile_version,
        )
        return {
            "updated": True,
            "transition_id": transition.id,
            "lifecycle_id": lifecycle.id,
        }


__all__ = ["UserReviewStateTracker"]
