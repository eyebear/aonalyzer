"""Phase 39, step 39.1 — persisted signal (recommendation) outcomes.

One row per ``(symbol, signal_date, horizon_days)`` so an outcome is never
duplicated for the same signal and horizon. Stores the forward stock return,
target/stop hits, and an option outcome that is recorded as *unavailable* (not
zero, not failed) unless real manual option data existed. Follows the Phase
9-37 lazy-table convention; no new Alembic revision.
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
    UniqueConstraint,
)

from app.database.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


# Option outcome statuses (never fabricated).
OPTION_OUTCOME_UNAVAILABLE = "OPTION_OUTCOME_UNAVAILABLE"
OPTION_OUTCOME_ESTIMATED = "OPTION_OUTCOME_ESTIMATED"

# How an ESTIMATED option outcome was derived. There is currently no
# market-priced basis: the platform has no historical option-chain feed, so an
# "estimated" return is a first-order delta approximation of the underlying's
# move (it ignores theta decay, gamma, and IV change). A future market-priced
# implementation should introduce ``OPTION_OUTCOME_BASIS_MARKET_PRICED`` and
# populate ``option_return_pct`` from real contract prices instead.
OPTION_OUTCOME_BASIS_DELTA_PROXY = "DELTA_APPROXIMATION_PROXY"
OPTION_OUTCOME_PROXY_NOTE = (
    "Estimated from the stock move via a first-order delta approximation — "
    "not market-priced option P&L. Ignores theta decay, gamma, and IV change."
)


class SignalOutcome(Base):
    """Forward outcome of one recommendation at one horizon."""

    __tablename__ = "signal_outcomes"

    id = Column(Integer, primary_key=True, index=True)

    symbol = Column(String(32), nullable=False, index=True)
    signal_date = Column(Date, nullable=False)
    horizon_days = Column(Integer, nullable=False)

    final_action_label = Column(String(64), nullable=True)
    instrument_scope = Column(String(32), nullable=True)
    direction = Column(String(16), nullable=True)

    entry_reference_price = Column(Float, nullable=True)
    target_price = Column(Float, nullable=True)
    stop_price = Column(Float, nullable=True)

    price_data_available = Column(Boolean, nullable=False, default=False)
    stock_return_pct = Column(Float, nullable=True)
    target_hit = Column(Boolean, nullable=True)
    stop_hit = Column(Boolean, nullable=True)
    bars_used = Column(Integer, nullable=False, default=0)

    option_outcome_status = Column(
        String(40), nullable=False, default=OPTION_OUTCOME_UNAVAILABLE
    )
    option_return_pct = Column(Float, nullable=True)
    manual_option_snapshot_id = Column(Integer, nullable=True)

    manual_trade_outcome = Column(String(32), nullable=True)

    context_json = Column(JSON, nullable=True)
    fed_to_memory = Column(Boolean, nullable=False, default=False)

    evaluated_at = Column(DateTime(timezone=True), nullable=True)
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
            "signal_date",
            "horizon_days",
            name="uq_signal_outcomes_symbol_date_horizon",
        ),
        Index("ix_signal_outcomes_symbol_date", "symbol", "signal_date"),
    )


__all__ = [
    "OPTION_OUTCOME_BASIS_DELTA_PROXY",
    "OPTION_OUTCOME_ESTIMATED",
    "OPTION_OUTCOME_PROXY_NOTE",
    "OPTION_OUTCOME_UNAVAILABLE",
    "SignalOutcome",
]
