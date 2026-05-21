"""Phase 25, steps 25.1 / 25.2 — persisted lifecycle tables.

* ``opportunity_lifecycle`` — current state per symbol (unique on symbol).
* ``opportunity_state_transitions`` — append-only audit trail.

Both follow the Phase 9-24 lazy-table convention.
"""

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
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


class OpportunityLifecycle(Base):
    """Persistent lifecycle envelope for a single symbol."""

    __tablename__ = "opportunity_lifecycle"

    id = Column(Integer, primary_key=True, index=True)

    symbol = Column(String(32), nullable=False, index=True)

    current_state = Column(String(64), nullable=False)
    previous_state = Column(String(64), nullable=True)
    last_transition_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    last_evaluated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    final_action_label = Column(String(64), nullable=True)

    user_review_status = Column(String(32), nullable=False, default="UNREVIEWED")
    user_reviewed_at = Column(DateTime(timezone=True), nullable=True)
    last_reactivation_at = Column(DateTime(timezone=True), nullable=True)

    profile_name = Column(String(128), nullable=True)
    profile_version = Column(String(128), nullable=True)
    context_json = Column(JSON, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    __table_args__ = (
        UniqueConstraint("symbol", name="uq_opportunity_lifecycle_symbol"),
        Index(
            "ix_opportunity_lifecycle_state",
            "current_state",
        ),
        Index(
            "ix_opportunity_lifecycle_review",
            "user_review_status",
        ),
    )


class OpportunityStateTransition(Base):
    """Append-only audit trail of state changes."""

    __tablename__ = "opportunity_state_transitions"

    id = Column(Integer, primary_key=True, index=True)

    symbol = Column(String(32), nullable=False, index=True)

    from_state = Column(String(64), nullable=True)
    to_state = Column(String(64), nullable=False)

    transition_reason_label = Column(String(128), nullable=False)
    transition_reason_summary = Column(Text, nullable=False)
    triggered_by = Column(String(32), nullable=False)
    source_phase = Column(String(64), nullable=False)
    final_action_label = Column(String(64), nullable=True)

    context_json = Column(JSON, nullable=True)
    profile_name = Column(String(128), nullable=True)
    profile_version = Column(String(128), nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        Index(
            "ix_opportunity_transitions_symbol_created",
            "symbol",
            "created_at",
        ),
    )


__all__ = ["OpportunityLifecycle", "OpportunityStateTransition"]
