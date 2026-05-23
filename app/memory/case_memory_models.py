"""Phase 41, step 41.1 — reusable historical case memory.

One row per ``(source_type, source_id)`` so a case is created once per source
outcome. Cases preserve the source reference, decision context, option-data
availability, outcome type, and a plain-language lesson. Follows the Phase 9-40
lazy-table convention; no new Alembic revision.
"""

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Date,
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


# Case types (Phase 41.6-41.8 + generic).
CASE_STOCK_RIGHT_OPTION_WRONG = "STOCK_RIGHT_OPTION_WRONG"
CASE_STOCK_RIGHT_OPTION_MISSING = "STOCK_RIGHT_OPTION_MISSING"
CASE_MANUAL_OPTION_ANALYSIS = "MANUAL_OPTION_ANALYSIS"
CASE_SIGNAL_OUTCOME = "SIGNAL_OUTCOME"
CASE_REJECTION_OUTCOME = "REJECTION_OUTCOME"
CASE_OVERRIDE = "OVERRIDE"
CASE_DO_NOT_TOUCH = "DO_NOT_TOUCH"

# Source discriminators.
SOURCE_SIGNAL = "SIGNAL_OUTCOME"
SOURCE_REJECTION = "REJECTION_OUTCOME"
SOURCE_OVERRIDE = "OVERRIDE_OUTCOME"


class CaseMemory(Base):
    __tablename__ = "case_memory"

    id = Column(Integer, primary_key=True, index=True)

    symbol = Column(String(32), nullable=False, index=True)
    case_type = Column(String(48), nullable=False)
    source_type = Column(String(32), nullable=False)
    source_id = Column(Integer, nullable=True)
    snapshot_date = Column(Date, nullable=True)

    outcome_type = Column(String(48), nullable=True)
    option_data_available = Column(Boolean, nullable=False, default=False)

    lesson_summary = Column(Text, nullable=True)
    decision_context_json = Column(JSON, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    __table_args__ = (
        UniqueConstraint("source_type", "source_id", name="uq_case_memory_source"),
        Index("ix_case_memory_symbol_type", "symbol", "case_type"),
    )


__all__ = [
    "CASE_DO_NOT_TOUCH",
    "CASE_MANUAL_OPTION_ANALYSIS",
    "CASE_OVERRIDE",
    "CASE_REJECTION_OUTCOME",
    "CASE_SIGNAL_OUTCOME",
    "CASE_STOCK_RIGHT_OPTION_MISSING",
    "CASE_STOCK_RIGHT_OPTION_WRONG",
    "CaseMemory",
    "SOURCE_OVERRIDE",
    "SOURCE_REJECTION",
    "SOURCE_SIGNAL",
]
