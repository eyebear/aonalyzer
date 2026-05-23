"""Phase 48 — memory package layout + validator.

Defines the export package's required files and validates a package's
structure before any import. The package is a directory containing JSONL data
files, a parquet embeddings file, two human/AI-readable markdown documents, and
a manifest.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PACKAGE_SCHEMA_VERSION = "aoao_memory_package_1.0"
MANIFEST_FILENAME = "manifest.json"

# JSONL data files the package must contain (Phase 48 spec).
REQUIRED_JSONL_FILES = [
    "manual_option_snapshots.jsonl",
    "option_ai_analysis.jsonl",
    "case_memory.jsonl",
    "signal_outcomes.jsonl",
    "rejection_outcomes.jsonl",
    "override_outcomes.jsonl",
    "do_not_touch_history.jsonl",
    "learning_reports.jsonl",
    "action_suggestions.jsonl",
    "lifecycle.jsonl",
    "versioned_decisions.jsonl",
]

REQUIRED_OTHER_FILES = [
    "memory_embeddings.parquet",
    "AI_MEMORY_SUMMARY.md",
    "AOAO_PLAYBOOK.md",
    MANIFEST_FILENAME,
]


@dataclass
class ValidationResult:
    valid: bool
    missing_files: list[str] = field(default_factory=list)
    invalid_files: list[str] = field(default_factory=list)
    schema_version: str | None = None
    record_counts: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "missing_files": list(self.missing_files),
            "invalid_files": list(self.invalid_files),
            "schema_version": self.schema_version,
            "record_counts": dict(self.record_counts),
        }


def validate_package(package_dir: str | Path) -> ValidationResult:
    """Validate a memory package directory's structure before import."""
    path = Path(package_dir)
    result = ValidationResult(valid=True)

    if not path.is_dir():
        return ValidationResult(valid=False, missing_files=[str(path)])

    # Manifest first.
    manifest_path = path / MANIFEST_FILENAME
    if not manifest_path.is_file():
        result.valid = False
        result.missing_files.append(MANIFEST_FILENAME)
    else:
        try:
            manifest = json.loads(manifest_path.read_text())
            result.schema_version = manifest.get("schema_version")
            result.record_counts = manifest.get("record_counts", {})
        except Exception:
            result.valid = False
            result.invalid_files.append(MANIFEST_FILENAME)

    for filename in REQUIRED_JSONL_FILES:
        fp = path / filename
        if not fp.is_file():
            result.valid = False
            result.missing_files.append(filename)
            continue
        # Each non-empty line must be valid JSON.
        try:
            for line in fp.read_text().splitlines():
                if line.strip():
                    json.loads(line)
        except Exception:
            result.valid = False
            result.invalid_files.append(filename)

    for filename in REQUIRED_OTHER_FILES:
        if filename == MANIFEST_FILENAME:
            continue
        if not (path / filename).is_file():
            result.valid = False
            result.missing_files.append(filename)

    return result


__all__ = [
    "MANIFEST_FILENAME",
    "PACKAGE_SCHEMA_VERSION",
    "REQUIRED_JSONL_FILES",
    "REQUIRED_OTHER_FILES",
    "ValidationResult",
    "validate_package",
]
