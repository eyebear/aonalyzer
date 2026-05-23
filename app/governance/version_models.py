"""Phase 46, steps 46.2-46.10 — governance version tables + audit metadata.

The Phase 0 ``version_registry`` (key/value) remains the live source the
version-stamp builder reads. These per-domain tables track the *history* of
each versioned artifact (rules, models, prompts, strategy profiles, data
schema, option parser), and ``decision_audit_metadata`` persists the version
stamp attached to every decision for auditability. Follows the Phase 9-45
lazy-table convention; no new Alembic revision.

Each table defines its own columns (no shared mixin) so SQLAlchemy maps each
table cleanly.
"""

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
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


class RuleVersion(Base):
    __tablename__ = "rule_versions"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=True)
    version = Column(String(64), nullable=False)
    description = Column(Text, nullable=True)
    is_current = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        UniqueConstraint("name", "version", name="uq_rule_versions_name_version"),
    )


class ModelVersion(Base):
    __tablename__ = "model_versions"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=True)
    version = Column(String(64), nullable=False)
    description = Column(Text, nullable=True)
    is_current = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        UniqueConstraint("name", "version", name="uq_model_versions_name_version"),
    )


class PromptVersion(Base):
    __tablename__ = "prompt_versions"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=True)
    version = Column(String(64), nullable=False)
    description = Column(Text, nullable=True)
    is_current = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        UniqueConstraint("name", "version", name="uq_prompt_versions_name_version"),
    )


# Phase 3 already owns ``strategy_profile_versions`` (StrategyProfileVersion in
# app.database.models). The governance layer reuses that table via
# ``app.database.models.StrategyProfileVersion`` rather than redefining it.


class DataSchemaVersion(Base):
    __tablename__ = "data_schema_versions"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=True)
    version = Column(String(64), nullable=False)
    description = Column(Text, nullable=True)
    is_current = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (UniqueConstraint("version", name="uq_data_schema_versions"),)


class OptionParserVersion(Base):
    __tablename__ = "option_parser_versions"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=True)
    version = Column(String(64), nullable=False)
    description = Column(Text, nullable=True)
    is_current = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (UniqueConstraint("version", name="uq_option_parser_versions"),)


class DecisionAuditMetadata(Base):
    """Phase 46.10 — the version stamp persisted per decision for audit."""

    __tablename__ = "decision_audit_metadata"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String(32), nullable=False, index=True)
    snapshot_date = Column(Date, nullable=False)
    version_stamp_json = Column(JSON, nullable=False, default=dict)
    is_compatible = Column(Boolean, nullable=False, default=True)
    missing_version_keys_json = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    __table_args__ = (
        UniqueConstraint("symbol", "snapshot_date", name="uq_decision_audit_symbol_date"),
        Index("ix_decision_audit_symbol_date", "symbol", "snapshot_date"),
    )


__all__ = [
    "DataSchemaVersion",
    "DecisionAuditMetadata",
    "ModelVersion",
    "OptionParserVersion",
    "PromptVersion",
    "RuleVersion",
]
