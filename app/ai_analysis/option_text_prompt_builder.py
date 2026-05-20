"""Structured manual-option-text prompt builder (Phase 18, step 18.9)."""

from __future__ import annotations

from typing import Any

from app.ai_analysis.prompt_versions import OPTION_TEXT_PROMPT_VERSION

_SYSTEM_PROMPT = (
    "You explain a single equity option contract pasted by a user. Respond with "
    "a SINGLE JSON object and nothing else (no prose, no code fences). Use exactly "
    "these keys, each a short plain-English string unless noted:\n"
    '  "plain_english_summary",\n'
    '  "liquidity_comment",\n'
    '  "greeks_comment",\n'
    '  "time_decay_comment",\n'
    '  "iv_comment",\n'
    '  "breakeven_comment",\n'
    '  "data_quality_warning",\n'
    '  "missing_fields": array of field-name strings that are absent,\n'
    '  "suggested_next_check",\n'
    '  "option_interpretation_label": a short UPPER_SNAKE_CASE label.\n'
    "Only describe what the data supports. Do not invent prices, Greeks, or IV."
)


def build_option_text_prompt(
    raw_text: str,
    parsed_fields: dict[str, Any] | None = None,
) -> tuple[str, str]:
    """Return (system_prompt, user_prompt) for free-form option text."""
    lines = ["Explain this pasted option contract.", "", "Raw text:", raw_text]

    if parsed_fields:
        lines.append("")
        lines.append("Already-parsed fields (may be partial):")
        for key in sorted(parsed_fields):
            value = parsed_fields[key]
            if value is not None and value != [] and value != {}:
                lines.append(f"  {key}: {value}")

    lines.append("")
    lines.append("Respond with the JSON object only.")
    return _SYSTEM_PROMPT, "\n".join(lines)


def option_text_prompt_version() -> str:
    return OPTION_TEXT_PROMPT_VERSION


__all__ = ["build_option_text_prompt", "option_text_prompt_version"]
