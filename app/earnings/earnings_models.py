from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)

from app.database.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class EarningsEvent(Base):
    """One earnings report record per (symbol, earnings_datetime_utc, source).

    Follows the Phase 7/8/9/11 convention: declared as a ``Base`` subclass and
    materialised on first use via ``Base.metadata.create_all``. No new Alembic
    revision; that follow-up should consolidate all post-0001 tables.
    """

    __tablename__ = "earnings_events"

    id = Column(Integer, primary_key=True, index=True)

    symbol = Column(String(32), nullable=False, index=True)
    earnings_datetime_utc = Column(DateTime(timezone=True), nullable=False, index=True)
    time_of_day = Column(String(32), nullable=False, default="UNKNOWN")
    confirmed = Column(Boolean, nullable=False, default=False)

    source = Column(String(64), nullable=False)
    source_url = Column(Text, nullable=True)
    source_title = Column(String(255), nullable=True)
    event_metadata_json = Column(JSON, nullable=True)

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
            "earnings_datetime_utc",
            "source",
            name="uq_earnings_events_symbol_datetime_source",
        ),
        Index(
            "ix_earnings_events_symbol_datetime",
            "symbol",
            "earnings_datetime_utc",
        ),
    )


class EarningsRiskSnapshot(Base):
    """Daily earnings-risk verdict per (symbol, snapshot_date)."""

    __tablename__ = "earnings_risk_snapshots"

    id = Column(Integer, primary_key=True, index=True)

    symbol = Column(String(32), nullable=False, index=True)
    snapshot_date = Column(Date, nullable=False)

    next_earnings_datetime_utc = Column(DateTime(timezone=True), nullable=True)
    days_to_earnings = Column(Integer, nullable=True)

    earnings_within_window = Column(Boolean, nullable=False, default=False)
    earnings_risk_window_days = Column(Integer, nullable=True)

    # Tri-state via string: "TRUE" | "FALSE" | "NOT_APPLICABLE". String is
    # chosen so the third state is encoded explicitly rather than via NULL,
    # because NULL would conflate "no info" with "no option supplied".
    earnings_before_expiration = Column(String(32), nullable=False, default="NOT_APPLICABLE")
    manual_option_expiration_date = Column(Date, nullable=True)

    risk_label = Column(String(64), nullable=False)
    risk_reason = Column(Text, nullable=True)
    data_sufficiency_status = Column(String(64), nullable=False, default="UNKNOWN")

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
            name="uq_earnings_risk_snapshots_symbol_date",
        ),
        Index(
            "ix_earnings_risk_snapshots_symbol_date",
            "symbol",
            "snapshot_date",
        ),
    )
