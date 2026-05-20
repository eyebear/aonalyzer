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


class MarketRegimeSnapshot(Base):
    """One persisted broad-market regime read per ``snapshot_date``.

    Follows the Phase 9-12 precedent: declared as a ``Base`` subclass and
    materialised on first use via ``Base.metadata.create_all`` (no new Alembic
    revision). Captures SPY/QQQ/IWM trend, VIX state, 10Y-yield pressure, and a
    composite regime label that supports both stock-only and option-aware
    decisions. Missing inputs are recorded as clean ``INSUFFICIENT_*`` states;
    no values are invented.
    """

    __tablename__ = "market_regime_snapshots"

    id = Column(Integer, primary_key=True, index=True)

    snapshot_date = Column(Date, nullable=False)
    source = Column(String(64), nullable=False, default="daily_prices")
    source_record_count = Column(Integer, nullable=False, default=0)

    # Index trends (SPY = broad market, QQQ = growth/tech, IWM = small-cap risk).
    spy_close = Column(Float, nullable=True)
    qqq_close = Column(Float, nullable=True)
    iwm_close = Column(Float, nullable=True)
    spy_trend = Column(String(16), nullable=False, default="UNKNOWN")
    qqq_trend = Column(String(16), nullable=False, default="UNKNOWN")
    iwm_trend = Column(String(16), nullable=False, default="UNKNOWN")
    index_uptrend_count = Column(Integer, nullable=False, default=0)
    index_downtrend_count = Column(Integer, nullable=False, default=0)

    # Volatility regime.
    vix_symbol = Column(String(32), nullable=True)
    vix_level = Column(Float, nullable=True)
    vix_state = Column(String(16), nullable=False, default="UNKNOWN")

    # 10Y-yield growth pressure.
    yield_symbol = Column(String(32), nullable=True)
    yield_level = Column(Float, nullable=True)
    yield_change_pct = Column(Float, nullable=True)
    yield_state = Column(String(16), nullable=False, default="UNKNOWN")
    yield_pressure = Column(Boolean, nullable=False, default=False)

    # Composite regime.
    regime_label = Column(String(16), nullable=False, default="UNKNOWN")
    regime_score = Column(Integer, nullable=False, default=0)

    data_sufficiency_status = Column(String(64), nullable=False, default="UNKNOWN")
    insufficient_reasons_json = Column(JSON, nullable=True)
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
            "snapshot_date",
            name="uq_market_regime_snapshots_date",
        ),
        Index(
            "ix_market_regime_snapshots_date",
            "snapshot_date",
        ),
    )


class SectorStrengthSnapshot(Base):
    """Relative strength of a sector ETF vs a benchmark per ``snapshot_date``.

    One row per (snapshot_date, sector_symbol, benchmark_symbol). Relative
    strength is the sector return minus the benchmark return over the configured
    lookback; ``rs_rank`` ranks sectors within a benchmark group (1 = strongest).
    """

    __tablename__ = "sector_strength_snapshots"

    id = Column(Integer, primary_key=True, index=True)

    snapshot_date = Column(Date, nullable=False)
    sector_symbol = Column(String(32), nullable=False, index=True)
    benchmark_symbol = Column(String(32), nullable=False)

    lookback_days = Column(Integer, nullable=False, default=0)
    source_record_count = Column(Integer, nullable=False, default=0)

    sector_return_pct = Column(Float, nullable=True)
    benchmark_return_pct = Column(Float, nullable=True)
    relative_strength = Column(Float, nullable=True)
    rs_rank = Column(Integer, nullable=True)
    trend = Column(String(16), nullable=False, default="UNKNOWN")

    data_sufficiency_status = Column(String(64), nullable=False, default="UNKNOWN")
    insufficient_reasons_json = Column(JSON, nullable=True)
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
            "snapshot_date",
            "sector_symbol",
            "benchmark_symbol",
            name="uq_sector_strength_date_symbol_benchmark",
        ),
        Index(
            "ix_sector_strength_date_symbol",
            "snapshot_date",
            "sector_symbol",
        ),
    )
