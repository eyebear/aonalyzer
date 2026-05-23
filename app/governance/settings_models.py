"""Phase 47 — runtime platform settings (key/value overrides).

Settings the user can change at runtime are persisted as typed key/value rows.
Defaults come from ``AppSettings``; a missing row means "use the default".
Follows the Phase 9-46 lazy-table convention; no new Alembic revision.
"""

from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    String,
    Text,
    UniqueConstraint,
)

from app.database.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PlatformSetting(Base):
    __tablename__ = "platform_settings"

    key = Column(String(128), primary_key=True)
    value = Column(Text, nullable=True)
    value_type = Column(String(16), nullable=False, default="str")
    updated_at = Column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    __table_args__ = (UniqueConstraint("key", name="uq_platform_settings_key"),)


__all__ = ["PlatformSetting"]
