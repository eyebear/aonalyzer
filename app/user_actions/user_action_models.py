"""Phase 38, steps 38.1-38.3 — user action / override / outcome tables.

* ``user_actions``    — every recorded user action (review/watch/ignore/reject/
  manual_trade/paste_option) with the system suggestion at the time.
* ``user_overrides``  — actions detected as going against the system suggestion.
* ``override_outcomes`` — the later-evaluated outcome of each override.

Follows the Phase 9-39 lazy-table convention; no new Alembic revision.
"""

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)

from app.database.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class UserAction(Base):
    __tablename__ = "user_actions"

    id = Column(Integer, primary_key=True, index=True)

    symbol = Column(String(32), nullable=False, index=True)
    action_type = Column(String(32), nullable=False)
    action_date = Column(Date, nullable=False)

    system_suggestion_label = Column(String(64), nullable=True)
    system_instrument_scope = Column(String(32), nullable=True)
    option_data_availability = Column(String(32), nullable=True)
    manual_option_snapshot_id = Column(Integer, nullable=True)

    notes = Column(Text, nullable=True)
    context_json = Column(JSON, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (Index("ix_user_actions_symbol_date", "symbol", "action_date"),)


class UserOverride(Base):
    __tablename__ = "user_overrides"

    id = Column(Integer, primary_key=True, index=True)

    user_action_id = Column(
        Integer, ForeignKey("user_actions.id", ondelete="CASCADE"), nullable=True
    )
    symbol = Column(String(32), nullable=False, index=True)
    override_type = Column(String(48), nullable=False)
    system_suggestion_label = Column(String(64), nullable=True)
    user_action_type = Column(String(32), nullable=False)
    signal_date = Column(Date, nullable=True)

    context_json = Column(JSON, nullable=True)
    detected_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)


class OverrideOutcome(Base):
    __tablename__ = "override_outcomes"

    id = Column(Integer, primary_key=True, index=True)

    user_override_id = Column(
        Integer, ForeignKey("user_overrides.id", ondelete="CASCADE"), nullable=True
    )
    symbol = Column(String(32), nullable=False, index=True)
    override_type = Column(String(48), nullable=False)
    horizon_days = Column(Integer, nullable=False)

    outcome_classification = Column(String(24), nullable=False, default="PENDING")
    stock_return_pct = Column(Float, nullable=True)
    target_hit = Column(Boolean, nullable=True)
    stop_hit = Column(Boolean, nullable=True)
    price_data_available = Column(Boolean, nullable=False, default=False)

    is_missed_opportunity = Column(Boolean, nullable=False, default=False)
    is_avoided_correctly = Column(Boolean, nullable=False, default=False)

    detail = Column(Text, nullable=True)
    context_json = Column(JSON, nullable=True)
    fed_to_memory = Column(Boolean, nullable=False, default=False)

    evaluated_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    __table_args__ = (
        Index("ix_override_outcomes_override", "user_override_id", "horizon_days"),
    )


__all__ = ["OverrideOutcome", "UserAction", "UserOverride"]
