"""Phase 42, step 42.2 — memory embeddings table.

Stores one embedding per ``(source_type, source_id)``. The vector is stored as
JSON so the table is portable across SQLite (tests) and PostgreSQL. On
PostgreSQL the pgvector extension can be enabled separately (best-effort) for
native vector ops; the deterministic Python cosine search works regardless.
Follows the Phase 9-41 lazy-table convention; no new Alembic revision.
"""

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Session

from app.database.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


# Embedded source types.
EMBED_CASE_MEMORY = "CASE_MEMORY"
EMBED_USER_FEEDBACK = "USER_FEEDBACK"
EMBED_REJECTED_CASE = "REJECTED_CASE"
EMBED_MANUAL_OPTION = "MANUAL_OPTION_SNAPSHOT"
EMBED_AI_SUMMARY = "AI_SUMMARY"
EMBED_ACTION_SUGGESTION = "ACTION_SUGGESTION"


class MemoryEmbedding(Base):
    __tablename__ = "memory_embeddings"

    id = Column(Integer, primary_key=True, index=True)

    source_type = Column(String(40), nullable=False)
    source_id = Column(Integer, nullable=True)
    symbol = Column(String(32), nullable=True, index=True)

    content_text = Column(Text, nullable=False)
    embedding_json = Column(JSON, nullable=False, default=list)
    dim = Column(Integer, nullable=False, default=0)
    model_name = Column(String(128), nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    __table_args__ = (
        UniqueConstraint("source_type", "source_id", name="uq_memory_embeddings_source"),
    )


def try_enable_pgvector(db: Session) -> bool:
    """Best-effort ``CREATE EXTENSION vector`` on PostgreSQL.

    Returns True if pgvector is available/enabled, False otherwise (e.g. on
    SQLite). Never raises — the JSON-backed cosine search is the portable path.
    """
    bind = db.get_bind()
    if bind.dialect.name != "postgresql":
        return False
    try:
        from sqlalchemy import text

        db.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        db.commit()
        return True
    except Exception:
        db.rollback()
        return False


__all__ = [
    "EMBED_ACTION_SUGGESTION",
    "EMBED_AI_SUMMARY",
    "EMBED_CASE_MEMORY",
    "EMBED_MANUAL_OPTION",
    "EMBED_REJECTED_CASE",
    "EMBED_USER_FEEDBACK",
    "MemoryEmbedding",
    "try_enable_pgvector",
]
