"""Phase 25, step 25.6 — Lifecycle history writer.

Single point that appends rows to ``opportunity_state_transitions``.
The state manager + reactivation engine + user review tracker + agent
job all delegate here so the audit trail is uniform.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.common.service_utils import ensure_tables
from app.lifecycle.lifecycle_models import OpportunityStateTransition


class LifecycleHistoryWriter:
    def append(
        self,
        db: Session,
        *,
        symbol: str,
        from_state: str | None,
        to_state: str,
        reason_label: str,
        reason_summary: str,
        triggered_by: str,
        source_phase: str,
        final_action_label: str | None = None,
        context: dict[str, Any] | None = None,
        profile_name: str | None = None,
        profile_version: str | None = None,
    ) -> OpportunityStateTransition:
        ensure_tables(db)
        clean = (symbol or "").strip().upper()
        if not clean:
            raise ValueError("symbol is required")
        if not to_state:
            raise ValueError("to_state is required")

        row = OpportunityStateTransition(
            symbol=clean,
            from_state=from_state,
            to_state=to_state,
            transition_reason_label=reason_label,
            transition_reason_summary=reason_summary,
            triggered_by=triggered_by,
            source_phase=source_phase,
            final_action_label=final_action_label,
            context_json=dict(context or {}),
            profile_name=profile_name,
            profile_version=profile_version,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row


__all__ = ["LifecycleHistoryWriter"]
