"""Phase 44, step 44.1 — weekly learning reports.

One row per ``(report_type, period_start, period_end)``. The full summary is a
self-describing JSON document. Follows the Phase 9-43 lazy-table convention; no
new Alembic revision.
"""

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Column,
    Date,
    DateTime,
    Integer,
    String,
    UniqueConstraint,
)

from app.database.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


REPORT_WEEKLY = "WEEKLY"


class LearningReport(Base):
    __tablename__ = "learning_reports"

    id = Column(Integer, primary_key=True, index=True)
    report_type = Column(String(24), nullable=False, default=REPORT_WEEKLY)
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)

    summary_json = Column(JSON, nullable=False, default=dict)

    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    __table_args__ = (
        UniqueConstraint(
            "report_type", "period_start", "period_end", name="uq_learning_reports_period"
        ),
    )


__all__ = ["REPORT_WEEKLY", "LearningReport"]
