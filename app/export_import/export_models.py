"""Phase 48, step 48.1 — export / import tracking tables.

Follows the Phase 9-47 lazy-table convention; no new Alembic revision.
"""

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Integer,
    String,
    Text,
)

from app.database.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ExportRun(Base):
    __tablename__ = "export_runs"

    id = Column(Integer, primary_key=True, index=True)
    package_path = Column(Text, nullable=False)
    status = Column(String(24), nullable=False, default="OK")
    file_count = Column(Integer, nullable=False, default=0)
    record_count = Column(Integer, nullable=False, default=0)
    manifest_json = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)


class ImportRun(Base):
    __tablename__ = "import_runs"

    id = Column(Integer, primary_key=True, index=True)
    package_path = Column(Text, nullable=False)
    status = Column(String(24), nullable=False, default="OK")
    records_imported = Column(Integer, nullable=False, default=0)
    validation_json = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)


__all__ = ["ExportRun", "ImportRun"]
