"""Phase 23, steps 23.1 / 23.2 — persisted rejected candidates + reasons.

* ``rejected_candidates`` — one row per ``(symbol, snapshot_date)``.
* ``rejection_reasons`` — many-to-one, FK to ``rejected_candidates.id``.

Both tables follow the Phase 9-22 lazy-table convention (no new Alembic
migration). The reason rows always include a category + source-phase so
later phases can replay the rejection trace without re-running the
Phase 20 / Phase 21 logic.
"""

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)

from app.database.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RejectedCandidate(Base):
    """Persisted rejection envelope per (symbol, snapshot_date)."""

    __tablename__ = "rejected_candidates"

    id = Column(Integer, primary_key=True, index=True)

    symbol = Column(String(32), nullable=False, index=True)
    snapshot_date = Column(Date, nullable=False)

    rejection_category = Column(String(64), nullable=False)
    rejection_severity = Column(String(32), nullable=False)
    final_action_label = Column(String(64), nullable=False)
    lifecycle_state = Column(String(32), nullable=False)

    is_rejected_but_interesting = Column(Boolean, nullable=False, default=False)
    interesting_reasons_json = Column(JSON, nullable=True)

    summary = Column(Text, nullable=False)
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
            name="uq_rejected_candidates_symbol_date",
        ),
        Index(
            "ix_rejected_candidates_symbol_date",
            "symbol",
            "snapshot_date",
        ),
        Index(
            "ix_rejected_candidates_interesting",
            "is_rejected_but_interesting",
        ),
    )


class RejectionReason(Base):
    """A single, structured rejection reason attached to a candidate."""

    __tablename__ = "rejection_reasons"

    id = Column(Integer, primary_key=True, index=True)

    rejected_candidate_id = Column(
        Integer,
        ForeignKey("rejected_candidates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    reason_label = Column(String(128), nullable=False)
    reason_category = Column(String(32), nullable=False)
    source_phase = Column(String(64), nullable=False)
    explanation = Column(Text, nullable=False)
    context_json = Column(JSON, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        Index(
            "ix_rejection_reasons_candidate_label",
            "rejected_candidate_id",
            "reason_label",
        ),
    )


__all__ = ["RejectedCandidate", "RejectionReason"]
