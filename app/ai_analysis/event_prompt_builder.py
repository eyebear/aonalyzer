"""Structured event prompt builder (Phase 18, step 18.1)."""

from __future__ import annotations

from typing import Any

from app.ai_analysis.prompt_versions import EVENT_ANALYSIS_PROMPT_VERSION

_SYSTEM_PROMPT = (
    "You are a financial event analyst. Read the event and respond with a SINGLE "
    "JSON object and nothing else (no prose, no code fences). Use exactly these "
    "keys:\n"
    '  "summary": string (2-3 sentences, factual),\n'
    '  "sentiment": one of "POSITIVE" | "NEGATIVE" | "NEUTRAL",\n'
    '  "price_impact": one of "PRICED_IN" | "PARTIALLY_PRICED_IN" | '
    '"NOT_PRICED_IN" | "UNKNOWN",\n'
    '  "key_points": array of short strings,\n'
    '  "risk_flags": array of short strings (may be empty),\n'
    '  "affected_symbols": array of ticker strings (may be empty),\n'
    '  "confidence": one of "LOW" | "MEDIUM" | "HIGH".\n'
    "Do not invent facts that are not supported by the event text."
)


def build_event_prompt(event: dict[str, Any]) -> tuple[str, str]:
    """Return (system_prompt, user_prompt) for an event dict."""
    lines = ["Analyze this market event:"]
    if event.get("symbol"):
        lines.append(f"Ticker: {event['symbol']}")
    if event.get("event_type"):
        lines.append(f"Event type: {event['event_type']}")
    if event.get("importance_level"):
        lines.append(f"Importance: {event['importance_level']}")
    if event.get("source"):
        lines.append(f"Source: {event['source']}")
    if event.get("event_time"):
        lines.append(f"Event time: {event['event_time']}")
    lines.append(f"Headline: {event.get('headline', '')}")
    if event.get("raw_summary"):
        lines.append(f"Details: {event['raw_summary']}")
    lines.append("")
    lines.append("Respond with the JSON object only.")
    return _SYSTEM_PROMPT, "\n".join(lines)


def event_prompt_version() -> str:
    return EVENT_ANALYSIS_PROMPT_VERSION


__all__ = ["build_event_prompt", "event_prompt_version"]
