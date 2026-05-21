"""Phase 24, steps 24.1 / 24.2 — persisted Do-Not-Touch tables.

* ``do_not_touch_items`` — one row per *currently-active* freeze. The
  symbol column carries a unique constraint so at most one active freeze
  exists per symbol at any time.
* ``do_not_touch_history`` — append-only audit log of every freeze /
  release / expiration event.

Both tables follow the Phase 9-23 lazy-table convention. The history
table intentionally has no FK back to ``do_not_touch_items`` because
items rows are deleted when a freeze is released (history outlives
items).
"""

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)

from app.database.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class DoNotTouchItem(Base):
    """An active freeze for a single symbol."""

    __tablename__ = "do_not_touch_items"

    id = Column(Integer, primary_key=True, index=True)

    symbol = Column(String(32), nullable=False, index=True)
    freeze_category = Column(String(64), nullable=False)
    freeze_severity = Column(String(32), nullable=False)

    frozen_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    expires_at = Column(DateTime(timezone=True), nullable=True)

    release_kind = Column(String(32), nullable=False)
    release_condition_label = Column(String(128), nullable=False)
    release_condition_description = Column(Text, nullable=False)

    reason_summary = Column(Text, nullable=False)
    source_phase = Column(String(64), nullable=False)
    triggered_by = Column(String(32), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)

    context_json = Column(JSON, nullable=True)
    profile_name = Column(String(128), nullable=True)
    profile_version = Column(String(128), nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    __table_args__ = (
        UniqueConstraint("symbol", name="uq_do_not_touch_items_symbol"),
        Index("ix_do_not_touch_items_active", "is_active"),
        Index("ix_do_not_touch_items_expires", "expires_at"),
    )


class DoNotTouchHistory(Base):
    """Append-only audit trail of every freeze / release / expiration."""

    __tablename__ = "do_not_touch_history"

    id = Column(Integer, primary_key=True, index=True)

    symbol = Column(String(32), nullable=False, index=True)
    event_type = Column(String(32), nullable=False, index=True)

    freeze_category = Column(String(64), nullable=False)
    freeze_severity = Column(String(32), nullable=False)

    frozen_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    released_at = Column(DateTime(timezone=True), nullable=True)

    release_reason = Column(Text, nullable=True)
    reason_summary = Column(Text, nullable=False)
    triggered_by = Column(String(32), nullable=False)
    source_phase = Column(String(64), nullable=False)

    context_json = Column(JSON, nullable=True)
    profile_name = Column(String(128), nullable=True)
    profile_version = Column(String(128), nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        Index(
            "ix_do_not_touch_history_symbol_created",
            "symbol",
            "created_at",
        ),
    )


__all__ = ["DoNotTouchHistory", "DoNotTouchItem"]
