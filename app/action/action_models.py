"""Phase 22, step 22.13 — persisted action suggestion packages.

One row per ``(symbol, snapshot_date)`` capturing the full Phase 22
package. Follows the Phase 9-21 lazy-table convention; no new Alembic
revision is added.
"""

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)

from app.database.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ActionSuggestion(Base):
    """Persisted Phase 22 action suggestion per (symbol, snapshot_date)."""

    __tablename__ = "action_suggestions"

    id = Column(Integer, primary_key=True, index=True)

    symbol = Column(String(32), nullable=False, index=True)
    snapshot_date = Column(Date, nullable=False)

    final_action_label = Column(String(64), nullable=False)
    instrument_scope = Column(String(32), nullable=False)
    lifecycle_state = Column(String(32), nullable=False)
    option_expression_status = Column(String(32), nullable=False)
    manual_option_input_needed = Column(Boolean, nullable=False, default=False)

    priority_score = Column(Float, nullable=True)
    confidence_score = Column(Float, nullable=True)
    suggested_action_summary = Column(Text, nullable=False)

    confidence_breakdown_json = Column(JSON, nullable=True)
    entry_condition_json = Column(JSON, nullable=False, default=dict)
    option_contract_criteria_json = Column(JSON, nullable=True)
    invalidation_condition_json = Column(JSON, nullable=False, default=dict)
    upgrade_condition_json = Column(JSON, nullable=False, default=dict)
    downgrade_condition_json = Column(JSON, nullable=False, default=dict)
    watch_condition_json = Column(JSON, nullable=False, default=dict)
    next_review_trigger_json = Column(JSON, nullable=False, default=dict)
    decision_trace_json = Column(JSON, nullable=False, default=list)
    version_stamp_json = Column(JSON, nullable=False, default=dict)
    action_items_json = Column(JSON, nullable=False, default=list)

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
            "snapshot_date",
            name="uq_action_suggestions_symbol_date",
        ),
        Index(
            "ix_action_suggestions_symbol_date",
            "symbol",
            "snapshot_date",
        ),
    )


__all__ = ["ActionSuggestion"]
