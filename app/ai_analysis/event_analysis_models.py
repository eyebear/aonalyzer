from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Integer,
    String,
    Text,
    UniqueConstraint,
)

from app.database.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class EventAnalysis(Base):
    """AI (or fallback) interpretation of one event (Phase 18, step 18.7).

    One analysis per event (``event_id`` unique). Declared as a ``Base`` subclass
    and materialised on first use via ``Base.metadata.create_all`` -- no new
    Alembic revision. ``is_fallback`` distinguishes a real AI answer from the
    deterministic fallback summary used when AI is disabled/unavailable.
    """

    __tablename__ = "event_analysis"

    id = Column(Integer, primary_key=True, index=True)

    event_id = Column(Integer, nullable=False, unique=True, index=True)
    symbol = Column(String(32), nullable=True, index=True)

    summary = Column(Text, nullable=True)
    sentiment = Column(String(16), nullable=True)
    price_impact = Column(String(32), nullable=True)
    importance_assessment = Column(String(255), nullable=True)
    confidence = Column(String(16), nullable=True)

    key_points_json = Column(JSON, nullable=True)
    risk_flags_json = Column(JSON, nullable=True)
    affected_symbols_json = Column(JSON, nullable=True)

    analysis_status = Column(String(16), nullable=False, default="FALLBACK")
    is_fallback = Column(Boolean, nullable=False, default=True)
    fallback_reason = Column(Text, nullable=True)

    provider_type = Column(String(64), nullable=True)
    model = Column(String(128), nullable=True)
    prompt_version = Column(String(128), nullable=True)
    raw_response = Column(Text, nullable=True)
    analysis_json = Column(JSON, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    __table_args__ = (
        UniqueConstraint("event_id", name="uq_event_analysis_event_id"),
    )
