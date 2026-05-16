from datetime import datetime, timezone

from sqlalchemy import (
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


class IvHistoryDay(Base):
    """One daily ATM-30d implied-vol row per (symbol, snapshot_date).

    IV history is **optional** in Aonalyzer. When this table is empty for a
    symbol, the IV risk service must surface IV_DATA_NOT_AVAILABLE — never a
    fabricated rank/percentile.
    """

    __tablename__ = "iv_history"

    id = Column(Integer, primary_key=True, index=True)

    symbol = Column(String(32), nullable=False, index=True)
    snapshot_date = Column(Date, nullable=False)

    atm_iv_30d = Column(Float, nullable=False)

    source = Column(String(64), nullable=False, default="placeholder")
    source_url = Column(Text, nullable=True)
    metadata_json = Column(JSON, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        UniqueConstraint(
            "symbol",
            "snapshot_date",
            name="uq_iv_history_symbol_date",
        ),
        Index(
            "ix_iv_history_symbol_date",
            "symbol",
            "snapshot_date",
        ),
    )


class IvRiskSnapshot(Base):
    """Daily IV risk verdict per (symbol, snapshot_date)."""

    __tablename__ = "iv_risk_snapshots"

    id = Column(Integer, primary_key=True, index=True)

    symbol = Column(String(32), nullable=False, index=True)
    snapshot_date = Column(Date, nullable=False)

    current_iv = Column(Float, nullable=True)
    iv_rank = Column(Float, nullable=True)
    iv_percentile = Column(Float, nullable=True)
    iv_history_days_used = Column(Integer, nullable=True)

    iv_warning_threshold = Column(Float, nullable=True)
    iv_reject_threshold = Column(Float, nullable=True)

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
            name="uq_iv_risk_snapshots_symbol_date",
        ),
        Index(
            "ix_iv_risk_snapshots_symbol_date",
            "symbol",
            "snapshot_date",
        ),
    )
