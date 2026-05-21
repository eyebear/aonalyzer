"""Phase 26, step 26.10 — Review queue generator.

Turns a fired ``EvaluatorResult`` into a ``ReviewQueueItem`` row,
idempotently: if there is already a ``PENDING`` or ``IN_REVIEW`` item
for the same ``(symbol, trigger_type)`` pair, the generator refreshes
it (updates the summary + context + priority) rather than enqueueing
a duplicate.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.common.service_utils import ensure_tables
from app.review.evaluators import EvaluatorResult
from app.review.review_models import ReviewQueueItem
from app.review.review_trigger_types import (
    ACTIVE_QUEUE_STATUSES,
    QUEUE_STATUS_PENDING,
    SOURCE_PHASE_ENGINE,
)


@dataclass
class GeneratedQueueItem:
    item: ReviewQueueItem
    is_new: bool

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.item.id, "is_new": self.is_new}


class ReviewQueueGenerator:
    def ensure_tables(self, db: Session) -> None:
        ensure_tables(db)

    def enqueue(
        self,
        db: Session,
        *,
        symbol: str,
        evaluator_result: EvaluatorResult,
        lifecycle_state: str | None = None,
        source_phase: str = SOURCE_PHASE_ENGINE,
        profile_name: str | None = None,
        profile_version: str | None = None,
        now: datetime | None = None,
    ) -> GeneratedQueueItem:
        self.ensure_tables(db)
        clean = (symbol or "").strip().upper()
        if not clean:
            raise ValueError("symbol is required")

        now = now or datetime.now(timezone.utc)

        existing = (
            db.query(ReviewQueueItem)
            .filter(ReviewQueueItem.symbol == clean)
            .filter(ReviewQueueItem.trigger_type == evaluator_result.trigger_type)
            .filter(ReviewQueueItem.status.in_(list(ACTIVE_QUEUE_STATUSES)))
            .order_by(ReviewQueueItem.id.desc())
            .first()
        )

        if existing is None:
            row = ReviewQueueItem(
                symbol=clean,
                trigger_type=evaluator_result.trigger_type,
                status=QUEUE_STATUS_PENDING,
                priority=evaluator_result.priority,
                summary=evaluator_result.summary,
                review_reason_label=evaluator_result.review_reason_label,
                context_json=dict(evaluator_result.context or {}),
                lifecycle_state=lifecycle_state,
                due_at=evaluator_result.due_at,
                source_phase=source_phase,
                profile_name=profile_name,
                profile_version=profile_version,
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            return GeneratedQueueItem(item=row, is_new=True)

        # Refresh existing pending/in-review item -- never enqueue a duplicate.
        existing.priority = evaluator_result.priority
        existing.summary = evaluator_result.summary
        existing.review_reason_label = evaluator_result.review_reason_label
        existing.context_json = dict(evaluator_result.context or {})
        existing.lifecycle_state = lifecycle_state
        existing.due_at = evaluator_result.due_at
        existing.profile_name = profile_name or existing.profile_name
        existing.profile_version = profile_version or existing.profile_version
        db.commit()
        db.refresh(existing)
        return GeneratedQueueItem(item=existing, is_new=False)


__all__ = ["GeneratedQueueItem", "ReviewQueueGenerator"]
