"""Phase 48, steps 48.14-48.15 — package validator + memory importer.

Validates a package's structure before restoring records. Importing is
additive and idempotent on natural keys where available; it never deletes
existing data. ORM-backed tables are restored from their JSONL files.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import Date, DateTime
from sqlalchemy.orm import Session

from app.common.service_utils import ensure_tables
from app.export_import.export_models import ImportRun
from app.export_import.memory_package import ValidationResult, validate_package
from app.learning.learning_report_models import LearningReport
from app.learning.rejection_outcome_models import RejectionOutcome
from app.learning.signal_outcome_models import SignalOutcome
from app.memory.case_memory_models import CaseMemory


@dataclass
class ImportResult:
    validation: ValidationResult
    imported: dict[str, int] = field(default_factory=dict)
    status: str = "OK"

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "validation": self.validation.to_dict(),
            "imported": dict(self.imported),
        }


# JSONL file -> (model, natural-key columns for idempotent restore).
_RESTORE_MAP: list[tuple[str, Any, tuple[str, ...]]] = [
    ("case_memory.jsonl", CaseMemory, ("source_type", "source_id")),
    ("signal_outcomes.jsonl", SignalOutcome, ("symbol", "signal_date", "horizon_days")),
    (
        "rejection_outcomes.jsonl",
        RejectionOutcome,
        ("symbol", "snapshot_date", "horizon_days", "source_type"),
    ),
    ("learning_reports.jsonl", LearningReport, ("report_type", "period_start", "period_end")),
]


class MemoryImporter:
    def ensure_tables(self, db: Session) -> None:
        ensure_tables(db)

    def import_package(self, db: Session, package_dir: str | Path) -> ImportResult:
        self.ensure_tables(db)
        validation = validate_package(package_dir)
        if not validation.valid:
            run = ImportRun(
                package_path=str(package_dir),
                status="INVALID",
                records_imported=0,
                validation_json=validation.to_dict(),
            )
            db.add(run)
            db.commit()
            return ImportResult(validation=validation, status="INVALID")

        path = Path(package_dir)
        imported: dict[str, int] = {}
        for filename, model, keys in _RESTORE_MAP:
            imported[filename] = self._restore_jsonl(db, path / filename, model, keys)
        db.commit()

        total = sum(imported.values())
        run = ImportRun(
            package_path=str(package_dir),
            status="OK",
            records_imported=total,
            validation_json=validation.to_dict(),
        )
        db.add(run)
        db.commit()
        return ImportResult(validation=validation, imported=imported, status="OK")

    def _restore_jsonl(
        self, db: Session, path: Path, model: Any, keys: tuple[str, ...]
    ) -> int:
        if not path.is_file():
            return 0
        columns = {c.name: c for c in model.__table__.columns}
        count = 0
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except Exception:
                continue
            # Drop the source primary key + unknown columns so inserts don't
            # collide on autoincrement ids across databases. Coerce ISO date /
            # datetime strings back to Python objects for typed columns.
            payload = {
                k: self._coerce(columns[k], v)
                for k, v in record.items()
                if k in columns and k != "id"
            }
            if not self._exists(db, model, keys, payload):
                db.add(model(**payload))
                count += 1
        return count

    def _coerce(self, column: Any, value: Any) -> Any:
        if value is None or not isinstance(value, str):
            return value
        col_type = column.type
        try:
            if isinstance(col_type, DateTime):
                return datetime.fromisoformat(value)
            if isinstance(col_type, Date):
                return date.fromisoformat(value)
        except ValueError:
            return value
        return value

    def _exists(
        self, db: Session, model: Any, keys: tuple[str, ...], payload: dict[str, Any]
    ) -> bool:
        if not keys:
            return False
        q = db.query(model)
        for key in keys:
            q = q.filter(getattr(model, key) == payload.get(key))
        return q.first() is not None


__all__ = ["ImportResult", "MemoryImporter"]
