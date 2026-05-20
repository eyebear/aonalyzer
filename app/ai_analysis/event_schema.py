"""Event analysis output schema (Phase 18, step 18.2).

Defines the JSON contract the AI must return for an event interpretation, plus a
result dataclass. Validation lives in ``schema_validator``; this module owns the
field names, allowed values, and coercion into a typed result.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.ai_analysis.schema_validator import coerce_str, coerce_str_list

# Analysis statuses (shared by event + option analysis).
AI_OK = "AI_OK"
FALLBACK = "FALLBACK"

SENTIMENT_VALUES = ["POSITIVE", "NEGATIVE", "NEUTRAL"]
PRICE_IMPACT_VALUES = ["PRICED_IN", "PARTIALLY_PRICED_IN", "NOT_PRICED_IN", "UNKNOWN"]
CONFIDENCE_VALUES = ["LOW", "MEDIUM", "HIGH"]

EVENT_REQUIRED_FIELDS = ["summary", "sentiment", "price_impact", "confidence"]
EVENT_LIST_FIELDS = ["key_points", "risk_flags", "affected_symbols"]
EVENT_ALLOWED_VALUES = {
    "sentiment": SENTIMENT_VALUES,
    "price_impact": PRICE_IMPACT_VALUES,
    "confidence": CONFIDENCE_VALUES,
}


def _normalize(value: Any, allowed: list[str], default: str) -> str:
    text = str(value).upper() if value is not None else ""
    return text if text in allowed else default


@dataclass(frozen=True)
class EventAnalysisResult:
    summary: str
    sentiment: str = "NEUTRAL"
    price_impact: str = "UNKNOWN"
    importance_assessment: str | None = None
    key_points: list[str] = field(default_factory=list)
    risk_flags: list[str] = field(default_factory=list)
    affected_symbols: list[str] = field(default_factory=list)
    confidence: str = "LOW"

    status: str = AI_OK
    provider_type: str | None = None
    model: str | None = None
    prompt_version: str | None = None
    fallback_reason: str | None = None
    raw_response: str | None = None

    @property
    def is_fallback(self) -> bool:
        return self.status == FALLBACK

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "sentiment": self.sentiment,
            "price_impact": self.price_impact,
            "importance_assessment": self.importance_assessment,
            "key_points": list(self.key_points),
            "risk_flags": list(self.risk_flags),
            "affected_symbols": list(self.affected_symbols),
            "confidence": self.confidence,
            "status": self.status,
            "is_fallback": self.is_fallback,
            "provider_type": self.provider_type,
            "model": self.model,
            "prompt_version": self.prompt_version,
            "fallback_reason": self.fallback_reason,
        }

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any],
        *,
        status: str = AI_OK,
        provider_type: str | None = None,
        model: str | None = None,
        prompt_version: str | None = None,
        raw_response: str | None = None,
    ) -> EventAnalysisResult:
        return cls(
            summary=coerce_str(payload.get("summary")),
            sentiment=_normalize(payload.get("sentiment"), SENTIMENT_VALUES, "NEUTRAL"),
            price_impact=_normalize(payload.get("price_impact"), PRICE_IMPACT_VALUES, "UNKNOWN"),
            importance_assessment=(
                coerce_str(payload.get("importance_assessment"))
                if payload.get("importance_assessment") is not None
                else None
            ),
            key_points=coerce_str_list(payload.get("key_points")),
            risk_flags=coerce_str_list(payload.get("risk_flags")),
            affected_symbols=coerce_str_list(payload.get("affected_symbols")),
            confidence=_normalize(payload.get("confidence"), CONFIDENCE_VALUES, "LOW"),
            status=status,
            provider_type=provider_type,
            model=model,
            prompt_version=prompt_version,
            raw_response=raw_response,
        )


__all__ = [
    "AI_OK",
    "CONFIDENCE_VALUES",
    "EVENT_ALLOWED_VALUES",
    "EVENT_LIST_FIELDS",
    "EVENT_REQUIRED_FIELDS",
    "FALLBACK",
    "PRICE_IMPACT_VALUES",
    "SENTIMENT_VALUES",
    "EventAnalysisResult",
]
