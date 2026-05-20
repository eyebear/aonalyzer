"""Prompt version registry (Phase 18, step 18.5).

Tracks the version of each prompt template so a decision/analysis snapshot can
record which prompt produced it. In-memory, optionally mirrored into
``version_registry`` as ``PROMPT`` entries.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

EVENT_ANALYSIS_PROMPT_VERSION = "event_analysis_prompt_v1"
OPTION_TEXT_PROMPT_VERSION = "option_text_prompt_v1"


@dataclass(frozen=True)
class PromptVersion:
    key: str
    version: str
    description: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"key": self.key, "version": self.version, "description": self.description}


_DEFAULTS = [
    PromptVersion("event_analysis", EVENT_ANALYSIS_PROMPT_VERSION,
                  "Structured prompt for high-importance event interpretation."),
    PromptVersion("option_text", OPTION_TEXT_PROMPT_VERSION,
                  "Structured prompt for manual option text explanation."),
]


class PromptVersionRegistry:
    def __init__(self, versions: list[PromptVersion] | None = None) -> None:
        self._versions: dict[str, PromptVersion] = {}
        for version in versions if versions is not None else _DEFAULTS:
            self._versions[version.key] = version

    def register(self, version: PromptVersion) -> None:
        self._versions[version.key] = version

    def get(self, key: str) -> PromptVersion | None:
        return self._versions.get(key)

    def version_of(self, key: str, default: str = "unknown_prompt_v0") -> str:
        found = self._versions.get(key)
        return found.version if found is not None else default

    def list_versions(self) -> list[PromptVersion]:
        return list(self._versions.values())

    def to_dict(self) -> dict[str, Any]:
        return {key: v.to_dict() for key, v in self._versions.items()}

    def persist_to_db(self, db: Session) -> int:
        inspector = inspect(db.get_bind())
        if "version_registry" not in inspector.get_table_names():
            return 0
        now = datetime.now(timezone.utc)
        written = 0
        for version in self._versions.values():
            key = f"prompt:{version.key}"
            existing = db.execute(
                text("SELECT id FROM version_registry WHERE version_key = :k"),
                {"k": key},
            ).first()
            if existing is None:
                db.execute(
                    text(
                        "INSERT INTO version_registry "
                        "(version_key, version_value, version_type, description, "
                        "is_active, created_at) "
                        "VALUES (:k, :v, 'PROMPT', :d, :a, :c)"
                    ),
                    {"k": key, "v": version.version, "d": version.description,
                     "a": True, "c": now},
                )
            else:
                db.execute(
                    text(
                        "UPDATE version_registry SET version_value = :v, "
                        "version_type = 'PROMPT', description = :d WHERE version_key = :k"
                    ),
                    {"k": key, "v": version.version, "d": version.description},
                )
            written += 1
        db.commit()
        return written


prompt_version_registry = PromptVersionRegistry()


__all__ = [
    "EVENT_ANALYSIS_PROMPT_VERSION",
    "OPTION_TEXT_PROMPT_VERSION",
    "PromptVersion",
    "PromptVersionRegistry",
    "prompt_version_registry",
]
