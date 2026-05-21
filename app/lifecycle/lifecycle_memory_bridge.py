"""Phase 25, step 25.9 — Lifecycle memory bridge.

When the case-memory / vector-memory store lands (planned for a later
phase), the bridge will push lifecycle "lessons" (e.g. "reactivated 12
days after rejection -- regime turned RISK_ON") into the memory index.

For Phase 25 the bridge writes the same lesson into the existing
``opportunity_state_transitions`` table under a dedicated reason label
so the audit trail captures it now and a future memory indexer can
walk those rows. No new tables are introduced for the placeholder.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.lifecycle.lifecycle_history_writer import LifecycleHistoryWriter
from app.lifecycle.lifecycle_states import (
    SOURCE_PHASE_REACTIVATION,
    TRIGGER_SYSTEM_REACTIVATION,
)


@dataclass(frozen=True)
class LifecycleLesson:
    symbol: str
    lesson_label: str
    summary: str
    context: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "lesson_label": self.lesson_label,
            "summary": self.summary,
            "context": dict(self.context),
        }


class LifecycleMemoryBridge:
    def __init__(
        self,
        history_writer: LifecycleHistoryWriter | None = None,
    ) -> None:
        self.history_writer = history_writer or LifecycleHistoryWriter()

    def record_lesson(
        self,
        db: Session,
        *,
        lesson: LifecycleLesson,
        current_state: str,
    ) -> dict[str, Any]:
        """Persist a lifecycle lesson as a transition row.

        The row's ``from_state`` and ``to_state`` are both set to the
        current state so the lesson never appears as a real transition;
        it is purely a memo. A later indexer can filter by
        ``transition_reason_label`` to pull only lesson rows.
        """
        row = self.history_writer.append(
            db=db,
            symbol=lesson.symbol,
            from_state=current_state,
            to_state=current_state,
            reason_label=f"LIFECYCLE_LESSON:{lesson.lesson_label}",
            reason_summary=lesson.summary,
            triggered_by=TRIGGER_SYSTEM_REACTIVATION,
            source_phase=SOURCE_PHASE_REACTIVATION,
            context={"lesson_label": lesson.lesson_label, **dict(lesson.context)},
        )
        return {"transition_id": row.id, "lesson": lesson.to_dict()}


__all__ = ["LifecycleLesson", "LifecycleMemoryBridge"]
