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


class TechnicalSnapshot(Base):
    """One persisted technical-indicator snapshot per (symbol, snapshot_date).

    Matches the existing project pattern (see ``FailedTickerLog`` and
    ``DataFreshness``) of declaring new tables as Base subclasses; the table is
    created on first use via ``Base.metadata.create_all`` from the service or
    route layer rather than via a new Alembic revision.
    """

    __tablename__ = "technical_snapshots"

    id = Column(Integer, primary_key=True, index=True)

    symbol = Column(String(32), nullable=False, index=True)
    snapshot_date = Column(Date, nullable=False)

    source = Column(String(64), nullable=False, default="daily_prices")
    source_record_count = Column(Integer, nullable=False, default=0)

    last_close = Column(Float, nullable=True)
    last_volume = Column(Float, nullable=True)

    sma_20 = Column(Float, nullable=True)
    sma_50 = Column(Float, nullable=True)
    sma_200 = Column(Float, nullable=True)

    ema_12 = Column(Float, nullable=True)
    ema_26 = Column(Float, nullable=True)

    rsi_14 = Column(Float, nullable=True)

    macd = Column(Float, nullable=True)
    macd_signal = Column(Float, nullable=True)
    macd_histogram = Column(Float, nullable=True)

    atr_14 = Column(Float, nullable=True)

    bollinger_upper = Column(Float, nullable=True)
    bollinger_middle = Column(Float, nullable=True)
    bollinger_lower = Column(Float, nullable=True)

    volume_ratio_20 = Column(Float, nullable=True)

    data_sufficiency_status = Column(String(64), nullable=False, default="UNKNOWN")
    insufficient_indicators_json = Column(JSON, nullable=True)
    notes = Column(Text, nullable=True)

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
            name="uq_technical_snapshots_symbol_date",
        ),
        Index(
            "ix_technical_snapshots_symbol_date",
            "symbol",
            "snapshot_date",
        ),
    )
