"""Phase 27, step 27.1 — persisted daily research worklist items.

One row per ``(worklist_date, symbol, source, worklist_type)`` so the same
practical task is never duplicated for the same symbol/source/type on the
same day. Follows the Phase 9-26 lazy-table convention (materialised via
``ensure_tables`` / ``Base.metadata.create_all``); no new Alembic revision.
"""

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Column,
    Date,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)

from app.database.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ResearchWorklistItem(Base):
    """A single daily research task surfaced on the Home command center."""

    __tablename__ = "research_worklist_items"

    id = Column(Integer, primary_key=True, index=True)

    worklist_date = Column(Date, nullable=False, index=True)
    symbol = Column(String(32), nullable=False, index=True)

    worklist_type = Column(String(48), nullable=False)
    source = Column(String(48), nullable=False)

    priority = Column(String(16), nullable=False, default="MEDIUM")
    rank = Column(Integer, nullable=False, default=0)

    title = Column(String(256), nullable=False)
    summary = Column(Text, nullable=False)
    context_json = Column(JSON, nullable=True)

    final_action_label = Column(String(64), nullable=True)
    lifecycle_state = Column(String(64), nullable=True)
    instrument_scope = Column(String(32), nullable=True)

    status = Column(String(16), nullable=False, default="OPEN", index=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolution_notes = Column(Text, nullable=True)

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
            "worklist_date",
            "symbol",
            "source",
            "worklist_type",
            name="uq_worklist_date_symbol_source_type",
        ),
        Index(
            "ix_worklist_date_status",
            "worklist_date",
            "status",
        ),
    )


__all__ = ["ResearchWorklistItem"]
