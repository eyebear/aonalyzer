"""Phase 21, step 21.12 — Version stamp builder.

Attaches rule / strategy-profile / model / prompt / data-schema /
decision-engine versions to every persisted decision. Reads from the
``version_registry`` table seeded in Phase 0; falls back to deterministic
defaults if a row is missing or the table cannot be read (e.g. unit
tests that drive the decision builder without a DB).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.database.models import VersionRegistry
from app.profiles.profile_models import StrategyProfile

# Phase 21 itself is the first real decision-engine release; the registry
# was seeded with the placeholder ``decision_engine_0.1`` in Phase 0.
DEFAULT_DECISION_ENGINE_VERSION = "decision_engine_0.1"
DEFAULT_RULE_VERSION = "ruleset_2026_05_v1"
DEFAULT_DATA_SCHEMA_VERSION = "aoao_schema_0.1"
DEFAULT_ACTION_SUGGESTION_VERSION = "action_suggestion_0.1"
DEFAULT_MODEL_VERSION = "deterministic_fallback"
DEFAULT_PROMPT_VERSION = "deterministic_fallback"


@dataclass(frozen=True)
class VersionStamp:
    rule_version: str
    strategy_profile_version: str
    data_schema_version: str
    decision_engine_version: str
    action_suggestion_version: str
    model_version: str
    prompt_version: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_version": self.rule_version,
            "strategy_profile_version": self.strategy_profile_version,
            "data_schema_version": self.data_schema_version,
            "decision_engine_version": self.decision_engine_version,
            "action_suggestion_version": self.action_suggestion_version,
            "model_version": self.model_version,
            "prompt_version": self.prompt_version,
        }


def build_version_stamp(
    *,
    db: Session | None,
    profile: StrategyProfile | None,
    model_version: str | None = None,
    prompt_version: str | None = None,
) -> VersionStamp:
    rule = _lookup(db, "rule_version", DEFAULT_RULE_VERSION)
    data_schema = _lookup(db, "data_schema_version", DEFAULT_DATA_SCHEMA_VERSION)
    engine = _lookup(db, "decision_engine_version", DEFAULT_DECISION_ENGINE_VERSION)
    action_suggestion = _lookup(
        db, "action_suggestion_version", DEFAULT_ACTION_SUGGESTION_VERSION
    )

    profile_version = (
        profile.profile_version
        if profile is not None
        else _lookup(db, "strategy_profile_version", "unknown_profile")
    )

    return VersionStamp(
        rule_version=rule,
        strategy_profile_version=profile_version,
        data_schema_version=data_schema,
        decision_engine_version=engine,
        action_suggestion_version=action_suggestion,
        model_version=model_version or DEFAULT_MODEL_VERSION,
        prompt_version=prompt_version or DEFAULT_PROMPT_VERSION,
    )


def _lookup(db: Session | None, key: str, default: str) -> str:
    if db is None:
        return default
    try:
        row: VersionRegistry | None = (
            db.query(VersionRegistry)
            .filter(VersionRegistry.version_key == key)
            .first()
        )
    except Exception:
        return default
    if row is None or not row.version_value:
        return default
    return str(row.version_value)


__all__ = [
    "DEFAULT_ACTION_SUGGESTION_VERSION",
    "DEFAULT_DATA_SCHEMA_VERSION",
    "DEFAULT_DECISION_ENGINE_VERSION",
    "DEFAULT_MODEL_VERSION",
    "DEFAULT_PROMPT_VERSION",
    "DEFAULT_RULE_VERSION",
    "VersionStamp",
    "build_version_stamp",
]
