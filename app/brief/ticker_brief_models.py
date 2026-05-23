"""Phase 28, step 28.1 — persisted one-page ticker briefs.

One row per ``(symbol, snapshot_date)``. The brief is an *assembled* view of
existing decision / action / rejection / lifecycle / review / event / memory /
confidence / version data — it is regenerated (upserted) on demand. Follows
the Phase 9-27 lazy-table convention; no new Alembic revision.
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
    UniqueConstraint,
)

from app.database.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TickerBrief(Base):
    """A persisted one-page brief for a symbol on a given snapshot date."""

    __tablename__ = "ticker_briefs"

    id = Column(Integer, primary_key=True, index=True)

    symbol = Column(String(32), nullable=False, index=True)
    snapshot_date = Column(Date, nullable=False)

    final_action_label = Column(String(64), nullable=False)
    instrument_scope = Column(String(32), nullable=True)
    lifecycle_state = Column(String(64), nullable=True)
    option_expression_status = Column(String(48), nullable=True)
    priority_score = Column(Float, nullable=True)
    confidence_score = Column(Float, nullable=True)

    # Each section is a self-describing dict; absent data is recorded honestly.
    sections_json = Column(JSON, nullable=False, default=dict)
    version_stamp_json = Column(JSON, nullable=False, default=dict)

    profile_name = Column(String(128), nullable=True)
    profile_version = Column(String(128), nullable=True)

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
            name="uq_ticker_briefs_symbol_date",
        ),
        Index(
            "ix_ticker_briefs_symbol_date",
            "symbol",
            "snapshot_date",
        ),
    )


__all__ = ["TickerBrief"]
