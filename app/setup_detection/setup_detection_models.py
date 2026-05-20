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


class StockSetupSignal(Base):
    """One detected stock setup signal per (symbol, snapshot_date).

    Phase 14 layer that classifies a setup *type* (PULLBACK_LONG, etc.) with a
    quality score from the Phase 11 technical snapshot, Phase 12 setup math, and
    Phase 13 regime/sector context. Distinct from the Phase 12 ``stock_setups``
    table (which holds the support/resistance/entry/target/stop math). Declared
    as a ``Base`` subclass and materialised on first use via
    ``Base.metadata.create_all`` -- no new Alembic revision.
    """

    __tablename__ = "stock_setup_signals"

    id = Column(Integer, primary_key=True, index=True)

    symbol = Column(String(32), nullable=False, index=True)
    snapshot_date = Column(Date, nullable=False)

    source = Column(String(64), nullable=False, default="technical+setup+regime")

    setup_type = Column(String(32), nullable=False, default="NO_TRADE")
    direction = Column(String(16), nullable=False, default="NONE")
    score = Column(Integer, nullable=False, default=0)

    # Snapshot of the key inputs used (for the decision trace / later layers).
    close = Column(Float, nullable=True)
    rsi_14 = Column(Float, nullable=True)
    atr_14 = Column(Float, nullable=True)
    risk_reward = Column(Float, nullable=True)
    nearest_support = Column(Float, nullable=True)
    nearest_resistance = Column(Float, nullable=True)
    entry_zone_low = Column(Float, nullable=True)
    entry_zone_high = Column(Float, nullable=True)
    target_price = Column(Float, nullable=True)
    stop_price = Column(Float, nullable=True)

    regime_label = Column(String(16), nullable=True)
    sector_symbol = Column(String(32), nullable=True)
    sector_trend = Column(String(16), nullable=True)
    sector_rs_rank = Column(Integer, nullable=True)

    data_sufficiency_status = Column(String(64), nullable=False, default="UNKNOWN")
    reasons_json = Column(JSON, nullable=True)
    components_json = Column(JSON, nullable=True)
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
            name="uq_stock_setup_signals_symbol_date",
        ),
        Index(
            "ix_stock_setup_signals_symbol_date",
            "symbol",
            "snapshot_date",
        ),
    )
