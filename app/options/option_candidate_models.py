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


class OptionCandidate(Base):
    """Stored result of evaluating one manually pasted option contract.

    Phase 15. One candidate per manual option snapshot (``manual_option_snapshot_id``
    is unique). Declared as a ``Base`` subclass and materialised on first use via
    ``Base.metadata.create_all`` -- no new Alembic revision. Missing-option-data
    evaluations are represented by the ``suitability_label`` rather than by the
    absence of a row, so the non-blocking states stay explicit.
    """

    __tablename__ = "option_candidates"

    id = Column(Integer, primary_key=True, index=True)

    symbol = Column(String(32), nullable=True, index=True)
    snapshot_date = Column(Date, nullable=False)
    manual_option_snapshot_id = Column(Integer, nullable=True, unique=True, index=True)

    option_type = Column(String(16), nullable=True)
    strike = Column(Float, nullable=True)
    expiration_date = Column(Date, nullable=True)
    dte = Column(Integer, nullable=True)

    premium = Column(Float, nullable=True)
    contract_cost = Column(Float, nullable=True)
    bid = Column(Float, nullable=True)
    ask = Column(Float, nullable=True)
    spread_percent = Column(Float, nullable=True)
    open_interest = Column(Integer, nullable=True)
    volume = Column(Integer, nullable=True)

    implied_volatility = Column(Float, nullable=True)
    iv_percent = Column(Float, nullable=True)
    iv_state = Column(String(16), nullable=True)

    breakeven = Column(Float, nullable=True)
    breakeven_distance_percent = Column(Float, nullable=True)
    target_price = Column(Float, nullable=True)
    target_margin_percent = Column(Float, nullable=True)

    liquidity_score = Column(Integer, nullable=True)

    suitability_label = Column(String(40), nullable=False, default="OPTION_DATA_NOT_AVAILABLE")
    is_suitable = Column(Boolean, nullable=False, default=False)
    data_sufficiency_status = Column(String(64), nullable=False, default="UNKNOWN")

    rejection_labels_json = Column(JSON, nullable=True)
    warning_labels_json = Column(JSON, nullable=True)
    outcomes_json = Column(JSON, nullable=True)
    earnings_risk_json = Column(JSON, nullable=True)
    reasons_json = Column(JSON, nullable=True)
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
            "manual_option_snapshot_id",
            name="uq_option_candidates_snapshot_id",
        ),
        Index(
            "ix_option_candidates_symbol_date",
            "symbol",
            "snapshot_date",
        ),
    )
