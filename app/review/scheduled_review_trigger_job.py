"""Phase 26, step 26.11 — Scheduled review trigger job.

Callable from the Phase 5 scheduler (or from the admin route) to:

1. Arm the appropriate triggers for every tracked symbol.
2. Evaluate every armed trigger and enqueue review items idempotently.

Reuses ``ReviewService.run_triggers`` for the heavy lifting; this
module exists so the scheduler integration point is its own callable
unit.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.common.service_utils import ensure_tables
from app.review.review_service import ReviewService, TriggerRunResult


@dataclass
class ScheduledRunResult:
    started_at: datetime
    finished_at: datetime
    inner: TriggerRunResult

    def to_dict(self) -> dict[str, Any]:
        return {
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat(),
            "result": self.inner.to_dict(),
        }


class ScheduledReviewTriggerJob:
    def __init__(self, service: ReviewService | None = None) -> None:
        self.service = service or ReviewService()

    def ensure_tables(self, db: Session) -> None:
        ensure_tables(db)

    def run(
        self,
        db: Session,
        *,
        symbols: list[str] | None = None,
    ) -> ScheduledRunResult:
        self.ensure_tables(db)
        started_at = datetime.now(timezone.utc)
        inner = self.service.run_triggers(db=db, symbols=symbols, now=started_at)
        finished_at = datetime.now(timezone.utc)
        return ScheduledRunResult(
            started_at=started_at, finished_at=finished_at, inner=inner
        )


__all__ = ["ScheduledRunResult", "ScheduledReviewTriggerJob"]
