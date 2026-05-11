from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String, Text, JSON

from app.database.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class DataFreshness(Base):
    __tablename__ = "data_freshness"

    id = Column(Integer, primary_key=True, index=True)
    data_category = Column(String(100), unique=True, nullable=False, index=True)

    latest_success_at = Column(DateTime(timezone=True), nullable=True)
    freshness_status = Column(String(50), nullable=False, default="UNKNOWN")
    max_age_minutes = Column(Integer, nullable=False, default=60)

    last_checked_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    details_json = Column(JSON, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )


class InsufficientDataEvent(Base):
    __tablename__ = "insufficient_data_events"

    id = Column(Integer, primary_key=True, index=True)

    label = Column(String(100), nullable=False, index=True)
    symbol = Column(String(50), nullable=True, index=True)
    data_category = Column(String(100), nullable=False, index=True)

    reason = Column(Text, nullable=False)
    severity = Column(String(50), nullable=False, default="BLOCKING")
    context_json = Column(JSON, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    resolved_at = Column(DateTime(timezone=True), nullable=True)