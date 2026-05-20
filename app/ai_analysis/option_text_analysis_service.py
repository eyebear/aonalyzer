"""Manual option text AI analysis (Phase 18, steps 18.9-18.11).

Builds a structured prompt from pasted option text, calls the AI provider
manager (OPTION_TEXT_READER task), validates the JSON against the 10-field
schema, and persists the explanation onto the existing
``manual_option_snapshots`` row (ai_status / ai_summary / ai_analysis_json).
When AI is unavailable or returns unusable output, the deterministic Phase 8
reader supplies the same-shaped fallback explanation.
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.ai_analysis.event_schema import AI_OK, FALLBACK
from app.ai_analysis.option_text_prompt_builder import (
    build_option_text_prompt,
    option_text_prompt_version,
)
from app.ai_analysis.option_text_schema import (
    OPTION_TEXT_LIST_FIELDS,
    OPTION_TEXT_REQUIRED_FIELDS,
    OptionTextAnalysisResult,
)
from app.ai_analysis.response_parser import extract_json
from app.ai_analysis.schema_validator import validate_schema
from app.ai_providers.provider_manager import AIProviderManager
from app.ai_providers.provider_types import TASK_OPTION_TEXT_READER
from app.core.config import AppSettings, get_settings
from app.options.manual_option_ai_reader import ManualOptionAiReader
from app.options.manual_option_input_service import ManualOptionInputService
from app.options.manual_option_models import ManualOptionSnapshotRecord


class OptionTextAnalysisService:
    def __init__(
        self,
        settings: AppSettings | None = None,
        provider_manager: AIProviderManager | None = None,
        manual_option_service: ManualOptionInputService | None = None,
        fallback_reader: ManualOptionAiReader | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.provider_manager = provider_manager or AIProviderManager(self.settings)
        self.manual_option_service = manual_option_service or ManualOptionInputService()
        self.fallback_reader = fallback_reader or ManualOptionAiReader()

    def analyze_snapshot(self, db: Session, snapshot_id: int) -> OptionTextAnalysisResult:
        record = self.manual_option_service.get_manual_snapshot_by_id(
            db=db, snapshot_id=snapshot_id
        )
        if record is None:
            raise ValueError(f"Manual option snapshot {snapshot_id} was not found.")

        result = self._run_ai_or_fallback(record)
        self._persist(db, snapshot_id, result)
        return result

    def _run_ai_or_fallback(
        self, record: ManualOptionSnapshotRecord
    ) -> OptionTextAnalysisResult:
        system_prompt, user_prompt = build_option_text_prompt(
            record.raw_text, parsed_fields=record.to_dict()
        )
        response = self.provider_manager.generate(
            TASK_OPTION_TEXT_READER, user_prompt, system_prompt=system_prompt
        )

        if response.is_ok and response.text:
            payload = extract_json(response.text)
            if payload is not None:
                validation = validate_schema(
                    payload,
                    required_fields=OPTION_TEXT_REQUIRED_FIELDS,
                    list_fields=OPTION_TEXT_LIST_FIELDS,
                )
                if validation.is_valid:
                    return OptionTextAnalysisResult.from_payload(
                        payload,
                        status=AI_OK,
                        provider_type=response.provider_type,
                        model=response.model,
                        prompt_version=option_text_prompt_version(),
                        raw_response=response.text,
                    )
            reason = "AI option output was not valid against the schema."
        else:
            reason = response.fallback_reason or f"AI status: {response.status}"

        # Deterministic fallback (Phase 8 reader produces the same 10 fields).
        fallback_payload = self.fallback_reader.analyze_snapshot(record)
        fallback_result = OptionTextAnalysisResult.from_payload(
            fallback_payload,
            status=FALLBACK,
            provider_type=response.provider_type,
            prompt_version=option_text_prompt_version(),
        )
        return replace(fallback_result, fallback_reason=reason)

    def _persist(
        self,
        db: Session,
        snapshot_id: int,
        result: OptionTextAnalysisResult,
    ) -> None:
        self.manual_option_service.ensure_manual_option_tables(db)
        db.execute(
            text(
                """
                UPDATE manual_option_snapshots
                SET ai_status = :ai_status,
                    ai_summary = :ai_summary,
                    ai_analysis_json = :ai_analysis_json,
                    updated_at = :updated_at
                WHERE id = :id
                """
            ),
            {
                "id": snapshot_id,
                "ai_status": result.status,
                "ai_summary": result.plain_english_summary,
                "ai_analysis_json": json.dumps(result.to_dict()),
                "updated_at": datetime.now(timezone.utc),
            },
        )
        db.commit()

    def get_stored_analysis(self, db: Session, snapshot_id: int) -> dict[str, Any] | None:
        record = self.manual_option_service.get_manual_snapshot_by_id(
            db=db, snapshot_id=snapshot_id
        )
        if record is None:
            return None
        return {
            "snapshot_id": snapshot_id,
            "ai_status": record.ai_status,
            "ai_summary": record.ai_summary,
            "ai_analysis": record.ai_analysis_json,
        }


__all__ = ["OptionTextAnalysisService"]
