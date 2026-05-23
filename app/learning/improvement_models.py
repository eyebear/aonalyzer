"""Phase 45, step 45.1 — improvement suggestions (approval-gated).

Improvement suggestions are observable and explainable proposals. They are
NEVER auto-applied: a suggestion stays PROPOSED until a user explicitly
approves it. Follows the Phase 9-44 lazy-table convention; no new Alembic
revision.
"""

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Index,
    Integer,
    String,
    Text,
)

from app.database.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


# Suggestion types (Phase 45.3-45.8).
SUGGEST_DTE = "DTE_CHANGE"
SUGGEST_IV_THRESHOLD = "IV_THRESHOLD_CHANGE"
SUGGEST_BREAKEVEN_MARGIN = "BREAKEVEN_MARGIN_CHANGE"
SUGGEST_MANUAL_OPTION_PROMPT = "MANUAL_OPTION_PROMPT_IMPROVEMENT"
SUGGEST_DO_NOT_TOUCH = "DO_NOT_TOUCH_CHANGE"
SUGGEST_OVERRIDE_BASED = "OVERRIDE_BASED_CHANGE"

# Statuses.
STATUS_PROPOSED = "PROPOSED"
STATUS_APPROVED = "APPROVED"
STATUS_REJECTED = "REJECTED"

ALL_STATUSES = frozenset({STATUS_PROPOSED, STATUS_APPROVED, STATUS_REJECTED})


class ImprovementSuggestion(Base):
    __tablename__ = "improvement_suggestions"

    id = Column(Integer, primary_key=True, index=True)

    suggestion_type = Column(String(48), nullable=False)
    title = Column(String(256), nullable=False)
    rationale = Column(Text, nullable=False)

    current_value = Column(String(128), nullable=True)
    proposed_value = Column(String(128), nullable=True)

    evidence_json = Column(JSON, nullable=True)
    comparison_json = Column(JSON, nullable=True)

    status = Column(String(16), nullable=False, default=STATUS_PROPOSED, index=True)
    decided_at = Column(DateTime(timezone=True), nullable=True)
    decided_by = Column(String(64), nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    __table_args__ = (Index("ix_improvement_suggestions_type_status", "suggestion_type", "status"),)


__all__ = [
    "ALL_STATUSES",
    "ImprovementSuggestion",
    "STATUS_APPROVED",
    "STATUS_PROPOSED",
    "STATUS_REJECTED",
    "SUGGEST_BREAKEVEN_MARGIN",
    "SUGGEST_DO_NOT_TOUCH",
    "SUGGEST_DTE",
    "SUGGEST_IV_THRESHOLD",
    "SUGGEST_MANUAL_OPTION_PROMPT",
    "SUGGEST_OVERRIDE_BASED",
]
