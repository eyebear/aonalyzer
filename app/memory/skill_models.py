"""Phase 43, steps 43.1-43.3 — skill registry / versions / performance / links.

Skills are named, versioned analysis capabilities. Performance metrics are
*recorded and exposed* — skill behavior is never silently changed based on
them. Follows the Phase 9-42 lazy-table convention; no new Alembic revision.
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
    Text,
    UniqueConstraint,
)

from app.database.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SkillRegistry(Base):
    __tablename__ = "skill_registry"

    id = Column(Integer, primary_key=True, index=True)
    skill_name = Column(String(64), nullable=False, unique=True)
    category = Column(String(48), nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)


class SkillVersion(Base):
    __tablename__ = "skill_versions"

    id = Column(Integer, primary_key=True, index=True)
    skill_name = Column(String(64), nullable=False, index=True)
    version = Column(String(32), nullable=False)
    is_current = Column(Boolean, nullable=False, default=True)
    definition_json = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        UniqueConstraint("skill_name", "version", name="uq_skill_versions_name_version"),
    )


class SkillLink(Base):
    __tablename__ = "skill_links"

    id = Column(Integer, primary_key=True, index=True)
    skill_name = Column(String(64), nullable=False, index=True)
    symbol = Column(String(32), nullable=False)
    snapshot_date = Column(Date, nullable=False)
    source_type = Column(String(40), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        UniqueConstraint(
            "skill_name", "symbol", "snapshot_date", name="uq_skill_links_key"
        ),
    )


class SkillPerformance(Base):
    __tablename__ = "skill_performance"

    id = Column(Integer, primary_key=True, index=True)
    skill_name = Column(String(64), nullable=False, index=True)
    skill_version = Column(String(32), nullable=True)

    sample_size = Column(Integer, nullable=False, default=0)
    target_hit_rate = Column(Float, nullable=True)
    stop_first_rate = Column(Float, nullable=True)
    stock_right_option_wrong_rate = Column(Float, nullable=True)
    manual_option_reader_usefulness = Column(Float, nullable=True)
    expected_value_proxy = Column(Float, nullable=True)

    context_json = Column(JSON, nullable=True)
    computed_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (Index("ix_skill_performance_name", "skill_name"),)


__all__ = ["SkillLink", "SkillPerformance", "SkillRegistry", "SkillVersion"]
