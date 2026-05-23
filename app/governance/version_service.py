"""Phase 46, steps 46.8-46.11 — version stamp wiring, compatibility, audit.

* ``compatibility_check`` validates a version stamp carries all eight required
  keys (Phase 46.11).
* ``write_audit`` persists the stamp per decision into
  ``decision_audit_metadata`` (Phase 46.10).
* ``seed_initial_versions`` records the current artifact versions in the
  per-domain history tables.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.common.service_utils import ensure_tables
from app.decision.version_stamp_builder import (
    DEFAULT_ACTION_SUGGESTION_VERSION,
    DEFAULT_DATA_SCHEMA_VERSION,
    DEFAULT_DECISION_ENGINE_VERSION,
    DEFAULT_MODEL_VERSION,
    DEFAULT_OPTION_PARSER_VERSION,
    DEFAULT_PROMPT_VERSION,
    DEFAULT_RULE_VERSION,
    REQUIRED_VERSION_KEYS,
)
from app.governance.version_models import (
    DataSchemaVersion,
    DecisionAuditMetadata,
    ModelVersion,
    OptionParserVersion,
    PromptVersion,
    RuleVersion,
)


@dataclass
class CompatibilityResult:
    is_compatible: bool
    missing_keys: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {"is_compatible": self.is_compatible, "missing_keys": list(self.missing_keys)}


def compatibility_check(version_stamp: dict[str, Any] | None) -> CompatibilityResult:
    stamp = version_stamp or {}
    missing = sorted(
        key for key in REQUIRED_VERSION_KEYS if not stamp.get(key)
    )
    return CompatibilityResult(is_compatible=not missing, missing_keys=missing)


class GovernanceService:
    def ensure_tables(self, db: Session) -> None:
        ensure_tables(db)

    def seed_initial_versions(self, db: Session) -> int:
        self.ensure_tables(db)
        created = 0
        created += self._seed_one(db, RuleVersion, version=DEFAULT_RULE_VERSION, name="ruleset")
        created += self._seed_one(
            db, ModelVersion, version=DEFAULT_MODEL_VERSION, name="model"
        )
        created += self._seed_one(
            db, PromptVersion, version=DEFAULT_PROMPT_VERSION, name="prompt"
        )
        created += self._seed_one(
            db, DataSchemaVersion, version=DEFAULT_DATA_SCHEMA_VERSION, name="data_schema"
        )
        created += self._seed_one(
            db,
            OptionParserVersion,
            version=DEFAULT_OPTION_PARSER_VERSION,
            name="manual_option_parser",
        )
        # ``strategy_profile_versions`` is seeded by the Phase 3 foundation; the
        # governance layer reads it rather than re-seeding it here.
        # action_suggestion + decision_engine recorded as rule-family rows.
        created += self._seed_one(
            db, RuleVersion, version=DEFAULT_ACTION_SUGGESTION_VERSION, name="action_suggestion"
        )
        created += self._seed_one(
            db, RuleVersion, version=DEFAULT_DECISION_ENGINE_VERSION, name="decision_engine"
        )
        db.commit()
        return created

    def _seed_one(self, db: Session, model, *, version: str, name: str | None) -> int:
        q = db.query(model).filter(model.version == version)
        if name is not None and hasattr(model, "name"):
            q = q.filter(model.name == name)
        if q.first() is not None:
            return 0
        db.add(model(version=version, name=name, is_current=True))
        return 1

    def write_audit(
        self,
        db: Session,
        *,
        symbol: str,
        snapshot_date: date,
        version_stamp: dict[str, Any],
    ) -> DecisionAuditMetadata:
        self.ensure_tables(db)
        compat = compatibility_check(version_stamp)
        existing = (
            db.query(DecisionAuditMetadata)
            .filter(DecisionAuditMetadata.symbol == symbol)
            .filter(DecisionAuditMetadata.snapshot_date == snapshot_date)
            .one_or_none()
        )
        if existing is None:
            row = DecisionAuditMetadata(
                symbol=symbol,
                snapshot_date=snapshot_date,
                version_stamp_json=version_stamp,
                is_compatible=compat.is_compatible,
                missing_version_keys_json=compat.missing_keys,
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            return row
        existing.version_stamp_json = version_stamp
        existing.is_compatible = compat.is_compatible
        existing.missing_version_keys_json = compat.missing_keys
        db.commit()
        db.refresh(existing)
        return existing


__all__ = ["CompatibilityResult", "GovernanceService", "compatibility_check"]
