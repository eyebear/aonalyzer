"""Phase 40, step 40.1 — persisted rejection / do-not-touch outcomes.

One row per ``(symbol, snapshot_date, horizon_days, source_type)``. Evaluates
whether a rejection or a freeze was useful, using forward returns. It never
backfills a fake option outcome: ``would_option_have_worked`` stays
``UNAVAILABLE`` unless real manual option data existed. Follows the Phase 9-39
lazy-table convention; no new Alembic revision.
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


SOURCE_REJECTION = "REJECTION"
SOURCE_DO_NOT_TOUCH = "DO_NOT_TOUCH"

WOULD_OPTION_UNAVAILABLE = "UNAVAILABLE"
WOULD_OPTION_TRUE = "TRUE"
WOULD_OPTION_FALSE = "FALSE"


class RejectionOutcome(Base):
    __tablename__ = "rejection_outcomes"

    id = Column(Integer, primary_key=True, index=True)

    symbol = Column(String(32), nullable=False, index=True)
    snapshot_date = Column(Date, nullable=False)
    horizon_days = Column(Integer, nullable=False)
    source_type = Column(String(24), nullable=False, default=SOURCE_REJECTION)

    category = Column(String(64), nullable=True)
    severity = Column(String(32), nullable=True)
    direction = Column(String(16), nullable=True)
    target_price = Column(Float, nullable=True)
    stop_price = Column(Float, nullable=True)

    price_data_available = Column(Boolean, nullable=False, default=False)
    stock_return_pct = Column(Float, nullable=True)
    would_stock_target_hit = Column(Boolean, nullable=True)
    stop_hit = Column(Boolean, nullable=True)
    bars_used = Column(Integer, nullable=False, default=0)

    option_data_available = Column(Boolean, nullable=False, default=False)
    would_option_have_worked = Column(
        String(16), nullable=False, default=WOULD_OPTION_UNAVAILABLE
    )

    was_rejection_correct = Column(Boolean, nullable=True)
    is_too_strict = Column(Boolean, nullable=False, default=False)

    detail = Column(Text, nullable=True)
    context_json = Column(JSON, nullable=True)
    fed_to_memory = Column(Boolean, nullable=False, default=False)

    evaluated_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    __table_args__ = (
        UniqueConstraint(
            "symbol",
            "snapshot_date",
            "horizon_days",
            "source_type",
            name="uq_rejection_outcomes_key",
        ),
        Index("ix_rejection_outcomes_symbol_date", "symbol", "snapshot_date"),
    )


__all__ = [
    "SOURCE_DO_NOT_TOUCH",
    "SOURCE_REJECTION",
    "WOULD_OPTION_FALSE",
    "WOULD_OPTION_TRUE",
    "WOULD_OPTION_UNAVAILABLE",
    "RejectionOutcome",
]
