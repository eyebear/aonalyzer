"""Phase 25, step 25.10 — Lifecycle update job.

Callable from the Phase 5 scheduler (or from an admin endpoint) to:

1. Re-evaluate every symbol that has an existing lifecycle row, applying
   any state transition that the latest Phase 22 package implies.
2. Run the reactivation engine for terminal-state symbols and reactivate
   any that have moved back into an active state.

The job is idempotent: re-running it on a stable set of symbols
produces no new transitions because the state manager short-circuits
no-op updates.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.common.service_utils import ensure_tables, load_watchlist_symbols
from app.lifecycle.lifecycle_models import OpportunityLifecycle
from app.lifecycle.lifecycle_service import LifecycleService


@dataclass
class LifecycleUpdateResult:
    started_at: datetime
    finished_at: datetime
    symbols_processed: int = 0
    transitions_recorded: int = 0
    reactivations: int = 0
    failed_symbols: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat(),
            "symbols_processed": self.symbols_processed,
            "transitions_recorded": self.transitions_recorded,
            "reactivations": self.reactivations,
            "failed_symbols": list(self.failed_symbols),
        }


class LifecycleUpdateJob:
    def __init__(self, service: LifecycleService | None = None) -> None:
        self.service = service or LifecycleService()

    def ensure_tables(self, db: Session) -> None:
        ensure_tables(db)

    def run(
        self,
        db: Session,
        *,
        symbols: list[str] | None = None,
        option_data_requested: bool = False,
    ) -> LifecycleUpdateResult:
        self.ensure_tables(db)
        started_at = datetime.now(timezone.utc)

        # Build the list of symbols to process.
        #
        # When the caller passes an explicit ``symbols`` list, use it
        # directly (the caller knows which symbols matter, even if there
        # is no lifecycle row yet and the watchlist seed has not been
        # loaded). Otherwise auto-discover from existing lifecycle rows +
        # the active watchlist.
        if symbols is not None:
            full = [s.strip().upper() for s in symbols if s and s.strip()]
        else:
            existing = [
                row.symbol for row in db.query(OpportunityLifecycle).all()
            ]
            watchlist = []
            try:
                watchlist = load_watchlist_symbols(db)
            except Exception:
                watchlist = []
            full = list(dict.fromkeys(existing + watchlist))

        result = LifecycleUpdateResult(
            started_at=started_at, finished_at=started_at
        )

        for symbol in full:
            try:
                evaluation = self.service.evaluate_symbol(
                    db=db,
                    symbol=symbol,
                    option_data_requested=option_data_requested,
                )
                result.symbols_processed += 1
                if evaluation.update.transition_id is not None:
                    result.transitions_recorded += 1
            except Exception:
                result.failed_symbols.append(symbol)
                continue

        # Reactivation sweep over terminal-state lifecycles.
        try:
            reactivations = self.service.detect_reactivations(
                db=db,
                option_data_requested=option_data_requested,
            )
            result.reactivations = len(reactivations)
        except Exception:
            pass

        result.finished_at = datetime.now(timezone.utc)
        return result


__all__ = ["LifecycleUpdateJob", "LifecycleUpdateResult"]
