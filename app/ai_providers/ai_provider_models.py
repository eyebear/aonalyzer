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


class AiProvider(Base):
    """Persisted configuration for one AI provider (Phase 17, step 17.13).

    Stores enable/active/fallback flags, endpoint, model, and the *name of the
    environment variable* that holds the API key -- never the key value itself.
    Declared as a ``Base`` subclass and materialised on first use via
    ``Base.metadata.create_all`` (no new Alembic revision).
    """

    __tablename__ = "ai_providers"

    id = Column(Integer, primary_key=True, index=True)

    provider_key = Column(String(64), nullable=False, unique=True, index=True)
    provider_type = Column(String(64), nullable=False)
    display_name = Column(String(128), nullable=False)

    is_enabled = Column(Boolean, nullable=False, default=True)
    is_active = Column(Boolean, nullable=False, default=False)
    is_fallback = Column(Boolean, nullable=False, default=False)

    base_url = Column(String(255), nullable=True)
    model = Column(String(128), nullable=True)
    api_key_env = Column(String(128), nullable=True)  # env var NAME, not the key

    config_json = Column(JSON, nullable=True)
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    __table_args__ = (
        UniqueConstraint("provider_key", name="uq_ai_providers_provider_key"),
    )
