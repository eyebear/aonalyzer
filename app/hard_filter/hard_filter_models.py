"""Phase 20 — persisted hard-filter results.

One row per ``(symbol, snapshot_date)`` capturing the gate's decision plus
the per-filter outcomes in JSON. Follows the Phase 9-15 pattern (declared
as a ``Base`` subclass, materialised on first use via ``ensure_tables`` /
``Base.metadata.create_all``; no new Alembic migration in this phase).
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


class HardFilterResult(Base):
    """Persisted hard-filter decision per (symbol, snapshot_date)."""

    __tablename__ = "hard_filter_results"

    id = Column(Integer, primary_key=True, index=True)

    symbol = Column(String(32), nullable=False, index=True)
    snapshot_date = Column(Date, nullable=False)

    # ``ALLOWED`` / ``BLOCKED`` -- the gate-level verdict for stock decisions.
    overall_decision = Column(String(32), nullable=False, default="ALLOWED")
    # ``OPTION_ALLOWED`` / ``OPTION_BLOCKED`` / ``OPTION_NOT_EVALUATED``.
    option_decision = Column(String(32), nullable=False, default="OPTION_NOT_EVALUATED")

    # Persist the filter outcomes as JSON so future phases can replay the
    # decision trace without re-evaluating. Each entry is a serialized
    # ``HardFilterOutcome`` dict.
    outcomes_json = Column(JSON, nullable=False, default=list)
    stock_blocking_labels_json = Column(JSON, nullable=False, default=list)
    option_blocking_labels_json = Column(JSON, nullable=False, default=list)
    warning_labels_json = Column(JSON, nullable=False, default=list)
    skipped_filters_json = Column(JSON, nullable=False, default=list)
    reasons_json = Column(JSON, nullable=False, default=list)

    profile_name = Column(String(128), nullable=True)
    profile_version = Column(String(128), nullable=True)

    # Quick-access scalars for dashboards and downstream phases.
    stock_risk_reward = Column(Float, nullable=True)
    price_extension_atr = Column(Float, nullable=True)
    price_extension_sma50_percent = Column(Float, nullable=True)
    regime_label = Column(String(32), nullable=True)
    earnings_risk_label = Column(String(64), nullable=True)

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
            name="uq_hard_filter_results_symbol_date",
        ),
        Index(
            "ix_hard_filter_results_symbol_date",
            "symbol",
            "snapshot_date",
        ),
    )


__all__ = ["HardFilterResult"]
