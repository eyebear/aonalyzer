"""Model version registry (Phase 16, step 16.6).

Tracks the name/version of each pretrained model the system can use. Kept
in-memory (no heavy imports) and optionally mirrored into the ``version_registry``
table as ``MODEL`` entries so a decision snapshot can record which model versions
were in effect.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session


@dataclass(frozen=True)
class ModelVersion:
    key: str          # stable identifier, e.g. "finbert"
    name: str         # model/repo name, e.g. "ProsusAI/finbert"
    version: str      # version string, e.g. "finbert_v1"
    model_type: str   # e.g. "SENTIMENT", "TEXT", "KLINE", "EMBEDDING"
    description: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "name": self.name,
            "version": self.version,
            "model_type": self.model_type,
            "description": self.description,
        }


_DEFAULT_VERSIONS = [
    ModelVersion("finbert", "ProsusAI/finbert", "finbert_v1", "SENTIMENT",
                 "Financial news sentiment classifier."),
    ModelVersion("fingpt", "FinGPT", "fingpt_placeholder_v0", "TEXT",
                 "Financial text analysis (placeholder)."),
    ModelVersion("kronos", "Kronos", "kronos_placeholder_v0", "KLINE",
                 "K-line auxiliary scoring (placeholder)."),
    ModelVersion("embeddings", "sentence-transformers/all-MiniLM-L6-v2",
                 "minilm_l6_v2", "EMBEDDING", "Sentence embeddings."),
]


class ModelVersionRegistry:
    def __init__(self, versions: list[ModelVersion] | None = None) -> None:
        self._versions: dict[str, ModelVersion] = {}
        for version in versions if versions is not None else _DEFAULT_VERSIONS:
            self._versions[version.key] = version

    def register(self, version: ModelVersion) -> None:
        self._versions[version.key] = version

    def get(self, key: str) -> ModelVersion | None:
        return self._versions.get(key)

    def list_versions(self) -> list[ModelVersion]:
        return list(self._versions.values())

    def to_dict(self) -> dict[str, Any]:
        return {key: version.to_dict() for key, version in self._versions.items()}

    def persist_to_db(self, db: Session) -> int:
        """Upsert each model version into ``version_registry`` as a MODEL entry.

        No-op (returns 0) if the table does not exist. Returns the number of rows
        inserted or updated.
        """
        inspector = inspect(db.get_bind())
        if "version_registry" not in inspector.get_table_names():
            return 0

        now = datetime.now(timezone.utc)
        written = 0
        for version in self._versions.values():
            version_key = f"model:{version.key}"
            existing = db.execute(
                text("SELECT id FROM version_registry WHERE version_key = :k"),
                {"k": version_key},
            ).first()

            if existing is None:
                db.execute(
                    text(
                        "INSERT INTO version_registry "
                        "(version_key, version_value, version_type, description, "
                        "is_active, created_at) "
                        "VALUES (:k, :v, :t, :d, :active, :created)"
                    ),
                    {
                        "k": version_key,
                        "v": version.version,
                        "t": "MODEL",
                        "d": version.description,
                        "active": True,
                        "created": now,
                    },
                )
            else:
                db.execute(
                    text(
                        "UPDATE version_registry "
                        "SET version_value = :v, version_type = :t, description = :d "
                        "WHERE version_key = :k"
                    ),
                    {
                        "k": version_key,
                        "v": version.version,
                        "t": "MODEL",
                        "d": version.description,
                    },
                )
            written += 1

        db.commit()
        return written


model_version_registry = ModelVersionRegistry()


__all__ = ["ModelVersion", "ModelVersionRegistry", "model_version_registry"]
