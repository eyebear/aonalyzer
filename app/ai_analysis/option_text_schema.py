"""Manual option text AI output schema (Phase 18, step 18.10).

The required structured explanation for a pasted option contract. Field set is
fixed (the 10 keys below); validation lives in ``schema_validator``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.ai_analysis.event_schema import AI_OK, FALLBACK
from app.ai_analysis.schema_validator import coerce_str, coerce_str_list

OPTION_TEXT_FIELDS = [
    "plain_english_summary",
    "liquidity_comment",
    "greeks_comment",
    "time_decay_comment",
    "iv_comment",
    "breakeven_comment",
    "data_quality_warning",
    "missing_fields",
    "suggested_next_check",
    "option_interpretation_label",
]

# A usable explanation must at least summarise and label the contract.
OPTION_TEXT_REQUIRED_FIELDS = ["plain_english_summary", "option_interpretation_label"]
OPTION_TEXT_LIST_FIELDS = ["missing_fields"]


@dataclass(frozen=True)
class OptionTextAnalysisResult:
    plain_english_summary: str
    option_interpretation_label: str
    liquidity_comment: str = ""
    greeks_comment: str = ""
    time_decay_comment: str = ""
    iv_comment: str = ""
    breakeven_comment: str = ""
    data_quality_warning: str = ""
    missing_fields: list[str] = field(default_factory=list)
    suggested_next_check: str = ""

    status: str = AI_OK
    provider_type: str | None = None
    model: str | None = None
    prompt_version: str | None = None
    fallback_reason: str | None = None
    raw_response: str | None = None

    @property
    def is_fallback(self) -> bool:
        return self.status == FALLBACK

    def to_payload(self) -> dict[str, Any]:
        """The 10 schema fields only (what gets stored as the AI explanation)."""
        return {
            "plain_english_summary": self.plain_english_summary,
            "liquidity_comment": self.liquidity_comment,
            "greeks_comment": self.greeks_comment,
            "time_decay_comment": self.time_decay_comment,
            "iv_comment": self.iv_comment,
            "breakeven_comment": self.breakeven_comment,
            "data_quality_warning": self.data_quality_warning,
            "missing_fields": list(self.missing_fields),
            "suggested_next_check": self.suggested_next_check,
            "option_interpretation_label": self.option_interpretation_label,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.to_payload(),
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
    ) -> OptionTextAnalysisResult:
        return cls(
            plain_english_summary=coerce_str(payload.get("plain_english_summary")),
            option_interpretation_label=coerce_str(
                payload.get("option_interpretation_label"), "OPTION_TEXT_REVIEWED"
            ),
            liquidity_comment=coerce_str(payload.get("liquidity_comment")),
            greeks_comment=coerce_str(payload.get("greeks_comment")),
            time_decay_comment=coerce_str(payload.get("time_decay_comment")),
            iv_comment=coerce_str(payload.get("iv_comment")),
            breakeven_comment=coerce_str(payload.get("breakeven_comment")),
            data_quality_warning=coerce_str(payload.get("data_quality_warning")),
            missing_fields=coerce_str_list(payload.get("missing_fields")),
            suggested_next_check=coerce_str(payload.get("suggested_next_check")),
            status=status,
            provider_type=provider_type,
            model=model,
            prompt_version=prompt_version,
            raw_response=raw_response,
        )


__all__ = [
    "OPTION_TEXT_FIELDS",
    "OPTION_TEXT_LIST_FIELDS",
    "OPTION_TEXT_REQUIRED_FIELDS",
    "OptionTextAnalysisResult",
]
