"""Phase 26 — DB-facing orchestrator for the Review Queue layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.common.service_utils import ensure_tables
from app.lifecycle.lifecycle_models import OpportunityLifecycle
from app.review.next_review_trigger_engine import (
    ArmingResult,
    FiredTrigger,
    NextReviewTriggerEngine,
)
from app.review.review_models import ReviewQueueItem, ReviewTrigger
from app.review.review_trigger_types import (
    ACTIVE_QUEUE_STATUSES,
    ALL_QUEUE_STATUSES,
    QUEUE_STATUS_DISMISSED,
    QUEUE_STATUS_IN_REVIEW,
    QUEUE_STATUS_PENDING,
    QUEUE_STATUS_RESOLVED,
)


@dataclass
class TriggerRunResult:
    arming_per_symbol: dict[str, ArmingResult] = field(default_factory=dict)
    fired: list[FiredTrigger] = field(default_factory=list)
    symbols_processed: int = 0
    queue_items_created: int = 0
    queue_items_refreshed: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbols_processed": self.symbols_processed,
            "queue_items_created": self.queue_items_created,
            "queue_items_refreshed": self.queue_items_refreshed,
            "arming": {
                symbol: arming.to_dict()
                for symbol, arming in self.arming_per_symbol.items()
            },
            "fired": [f.to_dict() for f in self.fired],
        }


class ReviewService:
    def __init__(
        self,
        engine: NextReviewTriggerEngine | None = None,
    ) -> None:
        self.engine = engine or NextReviewTriggerEngine()

    def ensure_tables(self, db: Session) -> None:
        ensure_tables(db)

    # ---------------------------------------------------------------- run

    def run_triggers(
        self,
        db: Session,
        *,
        symbols: list[str] | None = None,
        now: datetime | None = None,
    ) -> TriggerRunResult:
        self.ensure_tables(db)
        now = now or datetime.now(timezone.utc)

        # Resolve target symbols: when explicit, use the list; otherwise
        # pick every symbol with an existing lifecycle row.
        if symbols is not None:
            target_symbols = [
                s.strip().upper() for s in symbols if s and s.strip()
            ]
        else:
            target_symbols = [
                row.symbol
                for row in db.query(OpportunityLifecycle).all()
            ]

        result = TriggerRunResult(symbols_processed=len(target_symbols))
        for symbol in target_symbols:
            try:
                arming = self.engine.arm_for_symbol(db=db, symbol=symbol, now=now)
                result.arming_per_symbol[symbol] = arming
            except Exception:
                continue

        fired = self.engine.evaluate_armed(db=db, symbols=target_symbols, now=now)
        result.fired = fired
        for fire in fired:
            if fire.queue_item.is_new:
                result.queue_items_created += 1
            else:
                result.queue_items_refreshed += 1
        return result

    # ---------------------------------------------------------------- lookups

    def list_queue(
        self,
        db: Session,
        *,
        symbol: str | None = None,
        status: str | None = None,
        limit: int = 200,
    ) -> list[ReviewQueueItem]:
        self.ensure_tables(db)
        q = db.query(ReviewQueueItem)
        if symbol is not None:
            q = q.filter(ReviewQueueItem.symbol == symbol.strip().upper())
        if status is not None:
            q = q.filter(ReviewQueueItem.status == status.upper())
        return (
            q.order_by(
                ReviewQueueItem.status.asc(),
                ReviewQueueItem.priority.asc(),
                ReviewQueueItem.created_at.desc(),
            )
            .limit(limit)
            .all()
        )

    def list_active_queue(self, db: Session, limit: int = 200) -> list[ReviewQueueItem]:
        self.ensure_tables(db)
        return (
            db.query(ReviewQueueItem)
            .filter(ReviewQueueItem.status.in_(list(ACTIVE_QUEUE_STATUSES)))
            .order_by(
                ReviewQueueItem.priority.asc(),
                ReviewQueueItem.created_at.desc(),
            )
            .limit(limit)
            .all()
        )

    def get_by_id(self, db: Session, queue_id: int) -> ReviewQueueItem | None:
        self.ensure_tables(db)
        return db.query(ReviewQueueItem).filter(ReviewQueueItem.id == queue_id).one_or_none()

    def list_armed_triggers(
        self,
        db: Session,
        *,
        symbol: str | None = None,
    ) -> list[ReviewTrigger]:
        return self.engine.list_armed(db, symbol=symbol)

    # ---------------------------------------------------------------- mutate

    def transition_status(
        self,
        db: Session,
        queue_id: int,
        *,
        new_status: str,
        notes: str | None = None,
    ) -> ReviewQueueItem | None:
        self.ensure_tables(db)
        if new_status not in ALL_QUEUE_STATUSES:
            raise ValueError(f"unknown queue status '{new_status}'")
        item = self.get_by_id(db, queue_id)
        if item is None:
            return None
        item.status = new_status
        if new_status in (QUEUE_STATUS_RESOLVED, QUEUE_STATUS_DISMISSED):
            item.resolved_at = datetime.now(timezone.utc)
            item.resolution_notes = notes
        elif new_status == QUEUE_STATUS_PENDING:
            item.resolved_at = None
            item.resolution_notes = None
        elif new_status == QUEUE_STATUS_IN_REVIEW:
            item.resolved_at = None
        db.commit()
        db.refresh(item)
        return item


__all__ = ["ReviewService", "TriggerRunResult"]
