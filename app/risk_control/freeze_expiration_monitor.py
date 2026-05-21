"""Phase 24, step 24.6 — Freeze expiration monitor.

Sweeps ``do_not_touch_items`` for freezes whose ``expires_at`` is in
the past and releases them via the freeze manager. Each released item
generates an ``EXPIRED`` history entry (so the audit trail clearly
distinguishes auto-releases from user-initiated ones).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.common.service_utils import ensure_tables
from app.risk_control.do_not_touch_categories import (
    EVENT_EXPIRED,
    SOURCE_PHASE_EXPIRATION,
    TRIGGER_EXPIRATION_SWEEP,
)
from app.risk_control.do_not_touch_models import DoNotTouchItem
from app.risk_control.temporary_freeze_manager import TemporaryFreezeManager


@dataclass
class ExpirationSweepResult:
    swept_count: int = 0
    released_symbols: list[str] = field(default_factory=list)
    checked_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "swept_count": self.swept_count,
            "released_symbols": list(self.released_symbols),
            "checked_at": self.checked_at.isoformat()
            if self.checked_at is not None
            else None,
        }


class FreezeExpirationMonitor:
    def __init__(
        self,
        freeze_manager: TemporaryFreezeManager | None = None,
    ) -> None:
        self.freeze_manager = freeze_manager or TemporaryFreezeManager()

    def ensure_tables(self, db: Session) -> None:
        ensure_tables(db)

    def sweep_expired(
        self,
        db: Session,
        now: datetime | None = None,
    ) -> ExpirationSweepResult:
        self.ensure_tables(db)
        now = now or datetime.now(timezone.utc)

        # Items with a non-null expires_at strictly before ``now`` are due.
        expired_items: list[DoNotTouchItem] = (
            db.query(DoNotTouchItem)
            .filter(DoNotTouchItem.expires_at.isnot(None))
            .filter(DoNotTouchItem.expires_at < now)
            .all()
        )

        released: list[str] = []
        for item in expired_items:
            symbol = item.symbol
            release_reason = (
                f"Auto-released by expiration sweep at {now.isoformat()}. "
                f"Original release condition: {item.release_condition_label}."
            )
            self.freeze_manager.release(
                db=db,
                symbol=symbol,
                release_reason=release_reason,
                triggered_by=TRIGGER_EXPIRATION_SWEEP,
                source_phase=SOURCE_PHASE_EXPIRATION,
                event_type=EVENT_EXPIRED,
            )
            released.append(symbol)

        return ExpirationSweepResult(
            swept_count=len(released),
            released_symbols=released,
            checked_at=now,
        )


__all__ = ["ExpirationSweepResult", "FreezeExpirationMonitor"]
