"""Phase 24, step 24.4 — Temporary freeze manager.

Owns mutations on ``do_not_touch_items`` and writes the corresponding
history entries via ``DoNotTouchMemoryWriter``. Every mutation is
idempotent:

* ``freeze`` on a symbol that is already frozen with the same category
  is a no-op (with a RENEWED history entry only if the inputs changed).
* ``freeze`` on a symbol frozen under a *less severe* category upgrades
  it; a *more severe* category is preserved.
* ``release`` on a symbol with no active freeze is a no-op.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.common.service_utils import ensure_tables
from app.risk_control.do_not_touch_categories import (
    EVENT_FROZEN,
    EVENT_RELEASED,
    EVENT_RENEWED,
    SEVERITY_HARD_FREEZE,
    SEVERITY_SOFT_FREEZE,
    SOURCE_PHASE_CLASSIFIER,
    SOURCE_PHASE_MANUAL,
    TRIGGER_AUTOMATIC,
    TRIGGER_USER,
)
from app.risk_control.do_not_touch_memory_writer import (
    DoNotTouchMemoryWriter,
    utc_now,
)
from app.risk_control.do_not_touch_models import DoNotTouchItem
from app.risk_control.release_condition_builder import ReleaseCondition

_SEVERITY_RANK = {
    SEVERITY_SOFT_FREEZE: 1,
    SEVERITY_HARD_FREEZE: 2,
}


@dataclass
class FreezeOperationResult:
    item: DoNotTouchItem | None
    event_type: str | None  # FROZEN / RELEASED / RENEWED / None (no change)

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item.id if self.item is not None else None,
            "event_type": self.event_type,
        }


class TemporaryFreezeManager:
    def __init__(
        self,
        memory_writer: DoNotTouchMemoryWriter | None = None,
    ) -> None:
        self.memory_writer = memory_writer or DoNotTouchMemoryWriter()

    def ensure_tables(self, db: Session) -> None:
        ensure_tables(db)

    # ------------------------------------------------------------- freeze

    def freeze(
        self,
        db: Session,
        *,
        symbol: str,
        category: str,
        severity: str,
        release_condition: ReleaseCondition,
        reason_summary: str,
        triggered_by: str = TRIGGER_AUTOMATIC,
        source_phase: str = SOURCE_PHASE_CLASSIFIER,
        context: dict[str, Any] | None = None,
        profile_name: str | None = None,
        profile_version: str | None = None,
    ) -> FreezeOperationResult:
        self.ensure_tables(db)
        clean = (symbol or "").strip().upper()
        if not clean:
            raise ValueError("symbol is required")

        existing = (
            db.query(DoNotTouchItem)
            .filter(DoNotTouchItem.symbol == clean)
            .one_or_none()
        )

        now = utc_now()
        if existing is None:
            item = DoNotTouchItem(
                symbol=clean,
                freeze_category=category,
                freeze_severity=severity,
                frozen_at=now,
                expires_at=release_condition.expires_at,
                release_kind=release_condition.kind,
                release_condition_label=release_condition.label,
                release_condition_description=release_condition.description,
                reason_summary=reason_summary,
                source_phase=source_phase,
                triggered_by=triggered_by,
                is_active=True,
                context_json=dict(context or {}),
                profile_name=profile_name,
                profile_version=profile_version,
            )
            db.add(item)
            db.commit()
            db.refresh(item)

            self.memory_writer.append(
                db=db,
                symbol=clean,
                event_type=EVENT_FROZEN,
                freeze_category=category,
                freeze_severity=severity,
                reason_summary=reason_summary,
                triggered_by=triggered_by,
                source_phase=source_phase,
                frozen_at=now,
                expires_at=release_condition.expires_at,
                context=context,
                profile_name=profile_name,
                profile_version=profile_version,
            )
            return FreezeOperationResult(item=item, event_type=EVENT_FROZEN)

        # Existing freeze present -- decide whether to upgrade or preserve.
        if _is_upgrade(
            new_category=category,
            new_severity=severity,
            existing_category=existing.freeze_category,
            existing_severity=existing.freeze_severity,
        ):
            existing.freeze_category = category
            existing.freeze_severity = severity
            existing.frozen_at = now
            existing.expires_at = release_condition.expires_at
            existing.release_kind = release_condition.kind
            existing.release_condition_label = release_condition.label
            existing.release_condition_description = release_condition.description
            existing.reason_summary = reason_summary
            existing.source_phase = source_phase
            existing.triggered_by = triggered_by
            existing.context_json = dict(context or {})
            existing.profile_name = profile_name
            existing.profile_version = profile_version
            db.commit()
            db.refresh(existing)

            self.memory_writer.append(
                db=db,
                symbol=clean,
                event_type=EVENT_RENEWED,
                freeze_category=category,
                freeze_severity=severity,
                reason_summary=reason_summary,
                triggered_by=triggered_by,
                source_phase=source_phase,
                frozen_at=now,
                expires_at=release_condition.expires_at,
                context=context,
                profile_name=profile_name,
                profile_version=profile_version,
            )
            return FreezeOperationResult(item=existing, event_type=EVENT_RENEWED)

        # Idempotent no-op (existing freeze >= new in severity).
        return FreezeOperationResult(item=existing, event_type=None)

    # ------------------------------------------------------------- release

    def release(
        self,
        db: Session,
        *,
        symbol: str,
        release_reason: str,
        triggered_by: str = TRIGGER_USER,
        source_phase: str = SOURCE_PHASE_MANUAL,
        event_type: str = EVENT_RELEASED,
    ) -> FreezeOperationResult:
        self.ensure_tables(db)
        clean = (symbol or "").strip().upper()
        if not clean:
            raise ValueError("symbol is required")

        existing = (
            db.query(DoNotTouchItem)
            .filter(DoNotTouchItem.symbol == clean)
            .one_or_none()
        )
        if existing is None:
            return FreezeOperationResult(item=None, event_type=None)

        category = existing.freeze_category
        severity = existing.freeze_severity
        frozen_at = existing.frozen_at
        expires_at = existing.expires_at
        context = existing.context_json or {}
        profile_name = existing.profile_name
        profile_version = existing.profile_version

        db.delete(existing)
        db.commit()

        now = utc_now()
        self.memory_writer.append(
            db=db,
            symbol=clean,
            event_type=event_type,
            freeze_category=category,
            freeze_severity=severity,
            reason_summary=release_reason,
            triggered_by=triggered_by,
            source_phase=source_phase,
            frozen_at=frozen_at,
            expires_at=expires_at,
            released_at=now,
            release_reason=release_reason,
            context=context,
            profile_name=profile_name,
            profile_version=profile_version,
        )
        return FreezeOperationResult(item=None, event_type=event_type)

    # ------------------------------------------------------------- lookups

    def get_active(self, db: Session, symbol: str) -> DoNotTouchItem | None:
        clean = (symbol or "").strip().upper()
        if not clean:
            return None
        try:
            return (
                db.query(DoNotTouchItem)
                .filter(DoNotTouchItem.symbol == clean)
                .one_or_none()
            )
        except SQLAlchemyError:
            return None

    def is_frozen(self, db: Session, symbol: str) -> bool:
        return self.get_active(db, symbol) is not None


def _is_upgrade(
    *,
    new_category: str,
    new_severity: str,
    existing_category: str,
    existing_severity: str,
) -> bool:
    new_rank = _SEVERITY_RANK.get(new_severity, 0)
    existing_rank = _SEVERITY_RANK.get(existing_severity, 0)
    if new_rank > existing_rank:
        return True
    # Same severity but a different category triggers a renewal so the
    # history records the new reason.
    if new_rank == existing_rank and new_category != existing_category:
        return True
    return False


__all__ = ["FreezeOperationResult", "TemporaryFreezeManager"]
