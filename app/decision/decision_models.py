"""Phase 21, step 21.14 — persisted decision snapshots.

One row per ``(symbol, snapshot_date)`` capturing the full Phase 21
final decision. Follows the Phase 9-20 lazy-table convention; no new
Alembic revision is added.
"""

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
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


class DecisionSnapshot(Base):
    """Persisted Phase 21 decision per (symbol, snapshot_date)."""

    __tablename__ = "decision_snapshots"

    id = Column(Integer, primary_key=True, index=True)

    symbol = Column(String(32), nullable=False, index=True)
    snapshot_date = Column(Date, nullable=False)

    final_label = Column(String(64), nullable=False)
    rationale = Column(Text, nullable=True)

    stock_thesis_label = Column(String(64), nullable=False)
    option_expression_label = Column(String(64), nullable=False)
    instrument_scope = Column(String(32), nullable=False)
    event_risk_level = Column(String(16), nullable=False)
    memory_risk_level = Column(String(16), nullable=False)

    priority_score = Column(Float, nullable=True)
    confidence_score = Column(Float, nullable=True)

    confidence_breakdown_json = Column(JSON, nullable=True)
    checklist_json = Column(JSON, nullable=False, default=list)
    trace_json = Column(JSON, nullable=False, default=list)
    version_stamp_json = Column(JSON, nullable=False, default=dict)

    sufficiency_decision_json = Column(JSON, nullable=False, default=dict)
    hard_filter_decision_json = Column(JSON, nullable=False, default=dict)

    profile_name = Column(String(128), nullable=True)
    profile_version = Column(String(128), nullable=True)
    option_data_requested = Column(String(8), nullable=False, default="FALSE")

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
            name="uq_decision_snapshots_symbol_date",
        ),
        Index(
            "ix_decision_snapshots_symbol_date",
            "symbol",
            "snapshot_date",
        ),
    )


__all__ = ["DecisionSnapshot"]
