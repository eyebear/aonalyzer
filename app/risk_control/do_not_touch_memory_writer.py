"""Phase 24, step 24.8 — Do-Not-Touch memory writer.

Single point that appends to ``do_not_touch_history``. The freeze
manager and the expiration monitor both delegate here so the audit
trail is consistent (every freeze / release / renewal / expiration
event is recorded with the same fields).

A future memory phase can index these rows into the vector store; the
schema is already structured for that hand-off.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.common.service_utils import ensure_tables
from app.risk_control.do_not_touch_categories import (
    EVENT_EXPIRED,
    EVENT_FROZEN,
    EVENT_RELEASED,
    EVENT_RENEWED,
)
from app.risk_control.do_not_touch_models import DoNotTouchHistory


class DoNotTouchMemoryWriter:
    def append(
        self,
        db: Session,
        *,
        symbol: str,
        event_type: str,
        freeze_category: str,
        freeze_severity: str,
        reason_summary: str,
        triggered_by: str,
        source_phase: str,
        frozen_at: datetime | None = None,
        expires_at: datetime | None = None,
        released_at: datetime | None = None,
        release_reason: str | None = None,
        context: dict[str, Any] | None = None,
        profile_name: str | None = None,
        profile_version: str | None = None,
    ) -> DoNotTouchHistory:
        ensure_tables(db)
        clean = (symbol or "").strip().upper()
        if not clean:
            raise ValueError("symbol is required")
        if event_type not in (EVENT_FROZEN, EVENT_RELEASED, EVENT_RENEWED, EVENT_EXPIRED):
            raise ValueError(f"unknown event_type '{event_type}'")

        row = DoNotTouchHistory(
            symbol=clean,
            event_type=event_type,
            freeze_category=freeze_category,
            freeze_severity=freeze_severity,
            frozen_at=frozen_at,
            expires_at=expires_at,
            released_at=released_at,
            release_reason=release_reason,
            reason_summary=reason_summary,
            triggered_by=triggered_by,
            source_phase=source_phase,
            context_json=dict(context or {}),
            profile_name=profile_name,
            profile_version=profile_version,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


__all__ = ["DoNotTouchMemoryWriter", "utc_now"]
