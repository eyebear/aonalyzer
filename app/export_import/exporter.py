"""Phase 48, steps 48.2-48.13 — memory exporter.

Exports memory, action suggestions, manual option snapshots + AI analysis,
lifecycle, do-not-touch history, user overrides, outcomes, versioned decisions,
and embeddings into a self-describing package, plus AI_MEMORY_SUMMARY.md and
AOAO_PLAYBOOK.md. Writes only inside the given output directory.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.action.action_models import ActionSuggestion
from app.common.service_utils import ensure_tables
from app.decision.decision_models import DecisionSnapshot
from app.export_import.export_models import ExportRun
from app.export_import.memory_package import (
    MANIFEST_FILENAME,
    PACKAGE_SCHEMA_VERSION,
)
from app.learning.learning_report_models import LearningReport
from app.learning.rejection_outcome_models import RejectionOutcome
from app.learning.signal_outcome_models import SignalOutcome
from app.lifecycle.lifecycle_models import OpportunityLifecycle
from app.memory.case_memory_models import CaseMemory
from app.memory.memory_embedding_models import MemoryEmbedding
from app.options.manual_option_input_service import ManualOptionInputService
from app.risk_control.do_not_touch_models import DoNotTouchHistory
from app.user_actions.user_action_models import OverrideOutcome


def _jsonify(value: Any) -> Any:
    if isinstance(value, datetime | date):
        return value.isoformat()
    return value


def _row_to_dict(row: Any) -> dict[str, Any]:
    return {c.name: _jsonify(getattr(row, c.name)) for c in row.__table__.columns}


@dataclass
class ExportResult:
    package_path: str
    file_count: int
    record_count: int
    manifest: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "package_path": self.package_path,
            "file_count": self.file_count,
            "record_count": self.record_count,
            "manifest": self.manifest,
        }


class MemoryExporter:
    def __init__(self, manual_option_service: ManualOptionInputService | None = None) -> None:
        self.manual_option_service = manual_option_service or ManualOptionInputService()

    def ensure_tables(self, db: Session) -> None:
        ensure_tables(db)

    def export(self, db: Session, output_dir: str | Path) -> ExportResult:
        self.ensure_tables(db)
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        record_counts: dict[str, int] = {}

        # Manual option snapshots + AI analysis (from the raw-SQL table).
        snapshots = [
            s.to_dict()
            for s in self.manual_option_service.list_manual_snapshots(db=db, limit=100000)
        ]
        record_counts["manual_option_snapshots.jsonl"] = self._write_jsonl(
            out / "manual_option_snapshots.jsonl", snapshots
        )
        ai_rows = [
            {
                "id": s.get("id"),
                "symbol": s.get("symbol"),
                "ai_summary": s.get("ai_summary"),
                "ai_analysis": s.get("ai_analysis_json") or s.get("ai_analysis"),
            }
            for s in snapshots
        ]
        record_counts["option_ai_analysis.jsonl"] = self._write_jsonl(
            out / "option_ai_analysis.jsonl", ai_rows
        )

        # ORM-backed tables.
        table_files = [
            ("case_memory.jsonl", CaseMemory),
            ("signal_outcomes.jsonl", SignalOutcome),
            ("rejection_outcomes.jsonl", RejectionOutcome),
            ("override_outcomes.jsonl", OverrideOutcome),
            ("do_not_touch_history.jsonl", DoNotTouchHistory),
            ("learning_reports.jsonl", LearningReport),
            ("action_suggestions.jsonl", ActionSuggestion),
            ("lifecycle.jsonl", OpportunityLifecycle),
            ("versioned_decisions.jsonl", DecisionSnapshot),
        ]
        for filename, model in table_files:
            rows = [_row_to_dict(r) for r in db.query(model).all()]
            record_counts[filename] = self._write_jsonl(out / filename, rows)

        # Embeddings -> parquet (with a jsonl fallback if parquet unavailable).
        embeddings = [_row_to_dict(r) for r in db.query(MemoryEmbedding).all()]
        record_counts["memory_embeddings.parquet"] = self._write_parquet(
            out / "memory_embeddings.parquet", embeddings
        )

        # Human/AI-readable documents.
        self._write_text(out / "AI_MEMORY_SUMMARY.md", self._ai_memory_summary(db))
        self._write_text(out / "AOAO_PLAYBOOK.md", self._playbook(db))

        total_records = sum(record_counts.values())
        manifest = {
            "schema_version": PACKAGE_SCHEMA_VERSION,
            "created_at": datetime.now().isoformat(),
            "record_counts": record_counts,
            "total_records": total_records,
        }
        self._write_text(out / MANIFEST_FILENAME, json.dumps(manifest, indent=2))

        file_count = len(record_counts) + 3  # +2 md +1 manifest
        run = ExportRun(
            package_path=str(out),
            status="OK",
            file_count=file_count,
            record_count=total_records,
            manifest_json=manifest,
        )
        db.add(run)
        db.commit()

        return ExportResult(
            package_path=str(out),
            file_count=file_count,
            record_count=total_records,
            manifest=manifest,
        )

    # ---------------------------------------------------------------- writers

    def _write_jsonl(self, path: Path, rows: list[dict[str, Any]]) -> int:
        with path.open("w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row, default=str) + "\n")
        return len(rows)

    def _write_parquet(self, path: Path, rows: list[dict[str, Any]]) -> int:
        try:
            import pandas as pd

            df = pd.DataFrame(rows) if rows else pd.DataFrame(
                columns=["id", "source_type", "source_id", "symbol", "embedding_json"]
            )
            df.to_parquet(path, index=False)
            return len(rows)
        except Exception:
            # Fallback so the package always contains the file.
            with path.open("w", encoding="utf-8") as fh:
                for row in rows:
                    fh.write(json.dumps(row, default=str) + "\n")
            return len(rows)

    def _write_text(self, path: Path, text: str) -> None:
        path.write_text(text, encoding="utf-8")

    # --------------------------------------------------------------- documents

    def _ai_memory_summary(self, db: Session) -> str:
        cases = db.query(CaseMemory).all()
        by_type: dict[str, int] = {}
        for c in cases:
            by_type[c.case_type] = by_type.get(c.case_type, 0) + 1
        lines = ["# AI Memory Summary", ""]
        lines.append(f"Total cases: {len(cases)}")
        for case_type, count in sorted(by_type.items()):
            lines.append(f"- {case_type}: {count}")
        lines.append("")
        lines.append("## Recent lessons")
        for c in cases[:25]:
            lines.append(f"- [{c.symbol}] {c.lesson_summary or c.case_type}")
        return "\n".join(lines) + "\n"

    def _playbook(self, db: Session) -> str:
        reports = (
            db.query(LearningReport)
            .order_by(LearningReport.period_end.desc())
            .limit(5)
            .all()
        )
        lines = [
            "# AOAO Playbook",
            "",
            "The system's learned playbook, derived from tracked outcomes.",
            "",
            "## Core principles",
            "- Missing option data never blocks stock-only research.",
            "- Incomplete option data blocks option suitability only.",
            "- Option values are never invented.",
            "- Rejections and freezes are evaluated against real outcomes.",
            "",
            "## Recent weekly summaries",
        ]
        for r in reports:
            signals = json.dumps((r.summary_json or {}).get("signals", {}))
            lines.append(f"- {r.period_start} → {r.period_end}: {signals}")
        return "\n".join(lines) + "\n"


__all__ = ["ExportResult", "MemoryExporter"]
