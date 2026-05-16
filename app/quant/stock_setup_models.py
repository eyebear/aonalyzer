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


class StockSetup(Base):
    """One persisted stock setup per (symbol, snapshot_date).

    Follows the Phase 9/10/11 precedent: declared as a ``Base`` subclass and
    materialised on first use via ``Base.metadata.create_all``. No new Alembic
    revision is added here so the test/SQLite path stays parity-clean with the
    rest of the post-0001 tables.
    """

    __tablename__ = "stock_setups"

    id = Column(Integer, primary_key=True, index=True)

    symbol = Column(String(32), nullable=False, index=True)
    snapshot_date = Column(Date, nullable=False)

    source = Column(String(64), nullable=False, default="daily_prices+technical")
    source_record_count = Column(Integer, nullable=False, default=0)

    current_close = Column(Float, nullable=True)

    nearest_support = Column(Float, nullable=True)
    nearest_resistance = Column(Float, nullable=True)
    swing_low = Column(Float, nullable=True)
    swing_high = Column(Float, nullable=True)

    sma_20 = Column(Float, nullable=True)
    sma_50 = Column(Float, nullable=True)
    sma_200 = Column(Float, nullable=True)
    atr_14 = Column(Float, nullable=True)

    direction = Column(String(32), nullable=False, default="UNDEFINED")

    entry_zone_low = Column(Float, nullable=True)
    entry_zone_high = Column(Float, nullable=True)
    target_price = Column(Float, nullable=True)
    stop_price = Column(Float, nullable=True)
    stop_method = Column(String(32), nullable=False, default="UNDEFINED")

    risk_per_share = Column(Float, nullable=True)
    reward_per_share = Column(Float, nullable=True)
    stock_risk_reward = Column(Float, nullable=True)

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
            "symbol",
            "snapshot_date",
            name="uq_stock_setups_symbol_date",
        ),
        Index(
            "ix_stock_setups_symbol_date",
            "symbol",
            "snapshot_date",
        ),
    )
