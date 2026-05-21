"""Phase 26, steps 26.1 / 26.2 — persisted review trigger + queue tables.

* ``review_triggers`` — one row per *currently-armed* trigger condition
  per ``(symbol, trigger_type)``. The engine evaluates these on each run.
* ``review_queue`` — one row per *currently-pending* review item per
  ``(symbol, trigger_type)``. Resolved/dismissed items remain for audit.
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


class ReviewTrigger(Base):
    """An armed trigger condition for one symbol."""

    __tablename__ = "review_triggers"

    id = Column(Integer, primary_key=True, index=True)

    symbol = Column(String(32), nullable=False, index=True)
    trigger_type = Column(String(64), nullable=False)

    is_active = Column(Boolean, nullable=False, default=True)
    condition_json = Column(JSON, nullable=True)
    lifecycle_state = Column(String(64), nullable=True)

    last_evaluated_at = Column(DateTime(timezone=True), nullable=True)
    last_fired_at = Column(DateTime(timezone=True), nullable=True)
    fire_count = Column(Integer, nullable=False, default=0)

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
        UniqueConstraint(
            "symbol",
            "trigger_type",
            name="uq_review_triggers_symbol_type",
        ),
        Index(
            "ix_review_triggers_active",
            "is_active",
        ),
    )


class ReviewQueueItem(Base):
    """A queued review item awaiting user attention."""

    __tablename__ = "review_queue"

    id = Column(Integer, primary_key=True, index=True)

    symbol = Column(String(32), nullable=False, index=True)
    trigger_type = Column(String(64), nullable=False)

    status = Column(String(32), nullable=False, default="PENDING", index=True)
    priority = Column(String(16), nullable=False, default="MEDIUM")

    summary = Column(Text, nullable=False)
    review_reason_label = Column(String(128), nullable=False)
    context_json = Column(JSON, nullable=True)
    lifecycle_state = Column(String(64), nullable=True)

    due_at = Column(DateTime(timezone=True), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolution_notes = Column(Text, nullable=True)
    source_phase = Column(String(64), nullable=False, default="NEXT_REVIEW_TRIGGER_ENGINE")

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
        Index(
            "ix_review_queue_symbol_status",
            "symbol",
            "status",
        ),
        Index(
            "ix_review_queue_status_priority",
            "status",
            "priority",
        ),
    )


__all__ = ["ReviewQueueItem", "ReviewTrigger"]
