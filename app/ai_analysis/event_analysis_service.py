"""Event AI analysis orchestration (Phase 18, steps 18.6, 18.7, 18.8).

For high-importance events, builds a structured prompt, calls the AI provider
manager, safely parses + validates the JSON, and persists an ``EventAnalysis``.
When AI is disabled/unavailable or returns unusable output, a deterministic
fallback summary is stored instead -- the system always produces an analysis row
and never raises on the AI path.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.ai_analysis.event_analysis_models import EventAnalysis
from app.ai_analysis.event_prompt_builder import build_event_prompt, event_prompt_version
from app.ai_analysis.event_schema import (
    AI_OK,
    EVENT_ALLOWED_VALUES,
    EVENT_LIST_FIELDS,
    EVENT_REQUIRED_FIELDS,
    FALLBACK,
    EventAnalysisResult,
)
from app.ai_analysis.response_parser import extract_json
from app.ai_analysis.schema_validator import validate_schema
from app.ai_providers.provider_manager import AIProviderManager
from app.ai_providers.provider_types import TASK_EVENT_ANALYSIS
from app.common.service_utils import ensure_tables
from app.core.config import AppSettings, get_settings
from app.database.models import Event

_IMPORTANCE_RANK = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}


class EventAnalysisService:
    def __init__(
        self,
        settings: AppSettings | None = None,
        provider_manager: AIProviderManager | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.provider_manager = provider_manager or AIProviderManager(self.settings)

    def ensure_tables(self, db: Session) -> None:
        ensure_tables(db)

    def qualifies_for_analysis(self, importance_level: str | None) -> bool:
        min_rank = _IMPORTANCE_RANK.get(
            (self.settings.event_analysis_min_importance or "HIGH").upper(), 3
        )
        rank = _IMPORTANCE_RANK.get((importance_level or "").upper(), 0)
        return rank >= min_rank

    def _event_to_dict(self, event: Event) -> dict[str, Any]:
        return {
            "id": event.id,
            "symbol": event.symbol,
            "event_type": event.event_type,
            "importance_level": event.importance_level,
            "source": event.source,
            "event_time": event.event_time.isoformat() if event.event_time else None,
            "headline": event.headline,
            "raw_summary": event.raw_summary,
        }

    def _fallback_result(
        self,
        event: dict[str, Any],
        reason: str,
        provider_type: str | None,
    ) -> EventAnalysisResult:
        symbol = event.get("symbol") or "the market"
        importance = event.get("importance_level") or "UNCLASSIFIED"
        event_type = event.get("event_type") or "EVENT"
        headline = event.get("headline") or ""
        key_points = [p for p in [headline, event.get("source")] if p]
        return EventAnalysisResult(
            summary=f"[{importance} {event_type}] {symbol}: {headline}".strip(),
            sentiment="NEUTRAL",
            price_impact="UNKNOWN",
            key_points=key_points,
            confidence="LOW",
            status=FALLBACK,
            provider_type=provider_type,
            prompt_version=event_prompt_version(),
            fallback_reason=reason,
        )

    def analyze_event(self, db: Session, event_id: int) -> EventAnalysis:
        self.ensure_tables(db)

        event = db.query(Event).filter(Event.id == event_id).one_or_none()
        if event is None:
            raise ValueError(f"Event {event_id} was not found.")

        event_dict = self._event_to_dict(event)
        result = self._run_ai_or_fallback(event_dict)
        return self._persist(db, event.id, event.symbol, result)

    def analyze_high_importance(
        self,
        db: Session,
        limit: int = 20,
        *,
        only_unanalyzed: bool = True,
    ) -> dict[str, Any]:
        self.ensure_tables(db)

        events = (
            db.query(Event)
            .order_by(Event.detected_time.desc(), Event.id.desc())
            .limit(max(1, min(limit * 5, 500)))
            .all()
        )

        analyzed_ids = {
            row.event_id for row in db.query(EventAnalysis.event_id).all()
        }

        analyzed = 0
        skipped_low_importance = 0
        skipped_existing = 0
        results: list[dict[str, Any]] = []

        for event in events:
            if analyzed >= limit:
                break
            if not self.qualifies_for_analysis(event.importance_level):
                skipped_low_importance += 1
                continue
            if only_unanalyzed and event.id in analyzed_ids:
                skipped_existing += 1
                continue

            row = self._persist(
                db, event.id, event.symbol, self._run_ai_or_fallback(self._event_to_dict(event))
            )
            analyzed += 1
            results.append({"event_id": event.id, "status": row.analysis_status})

        return {
            "analyzed": analyzed,
            "skipped_low_importance": skipped_low_importance,
            "skipped_existing": skipped_existing,
            "results": results,
        }

    def _run_ai_or_fallback(self, event_dict: dict[str, Any]) -> EventAnalysisResult:
        system_prompt, user_prompt = build_event_prompt(event_dict)
        response = self.provider_manager.generate(
            TASK_EVENT_ANALYSIS, user_prompt, system_prompt=system_prompt
        )

        if not response.is_ok or not response.text:
            return self._fallback_result(
                event_dict,
                reason=response.fallback_reason or f"AI status: {response.status}",
                provider_type=response.provider_type,
            )

        payload = extract_json(response.text)
        if payload is None:
            return self._fallback_result(
                event_dict,
                reason="AI response was not parseable JSON.",
                provider_type=response.provider_type,
            )

        validation = validate_schema(
            payload,
            required_fields=EVENT_REQUIRED_FIELDS,
            list_fields=EVENT_LIST_FIELDS,
            allowed_values=EVENT_ALLOWED_VALUES,
        )
        if not validation.is_valid:
            return self._fallback_result(
                event_dict,
                reason="AI output failed schema validation: " + "; ".join(validation.errors),
                provider_type=response.provider_type,
            )

        return EventAnalysisResult.from_payload(
            payload,
            status=AI_OK,
            provider_type=response.provider_type,
            model=response.model,
            prompt_version=event_prompt_version(),
            raw_response=response.text,
        )

    def _persist(
        self,
        db: Session,
        event_id: int,
        symbol: str | None,
        result: EventAnalysisResult,
    ) -> EventAnalysis:
        existing = (
            db.query(EventAnalysis)
            .filter(EventAnalysis.event_id == event_id)
            .one_or_none()
        )

        values = {
            "symbol": symbol,
            "summary": result.summary,
            "sentiment": result.sentiment,
            "price_impact": result.price_impact,
            "importance_assessment": result.importance_assessment,
            "confidence": result.confidence,
            "key_points_json": list(result.key_points),
            "risk_flags_json": list(result.risk_flags),
            "affected_symbols_json": list(result.affected_symbols),
            "analysis_status": result.status,
            "is_fallback": result.is_fallback,
            "fallback_reason": result.fallback_reason,
            "provider_type": result.provider_type,
            "model": result.model,
            "prompt_version": result.prompt_version,
            "raw_response": result.raw_response,
            "analysis_json": result.to_dict(),
        }

        if existing is None:
            row = EventAnalysis(event_id=event_id, **values)
            db.add(row)
            db.commit()
            db.refresh(row)
            return row

        for key, value in values.items():
            setattr(existing, key, value)
        db.commit()
        db.refresh(existing)
        return existing


__all__ = ["EventAnalysisService"]
