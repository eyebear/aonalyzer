"""Phase 37, steps 37.3 / 37.13 — source retriever + citation builder.

The source retriever lists the records that informed an answer; the citation
builder turns the context into a list of explicit citations naming the fields
used. This keeps the chat auditable: the user can always see what the answer
was grounded in (and that no external/invented data was used).
"""

from __future__ import annotations

from typing import Any

from app.chat.context_builder import ChatContext


def retrieve_sources(context: ChatContext) -> list[dict[str, Any]]:
    """List the records that grounded the answer (Phase 37.3)."""
    sources: list[dict[str, Any]] = []
    if context.final_action_label is not None:
        sources.append(
            {
                "source_type": "DECISION",
                "symbol": context.symbol,
                "final_action_label": context.final_action_label,
            }
        )
    if context.manual_option is not None:
        sources.append(
            {
                "source_type": "MANUAL_OPTION_SNAPSHOT",
                "option_data_status": context.option_data_status,
            }
        )
    for event in context.events:
        sources.append({"source_type": "EVENT", **event})
    if context.earnings is not None:
        sources.append({"source_type": "EARNINGS", **context.earnings})
    if context.iv is not None:
        sources.append({"source_type": "IV", **context.iv})
    for case in context.similar_cases:
        sources.append({"source_type": "CASE_MEMORY", **case})
    return sources


def build_citations(context: ChatContext) -> list[dict[str, Any]]:
    """Build explicit field-level citations from the context (Phase 37.13)."""
    citations: list[dict[str, Any]] = []
    if context.final_action_label is not None:
        citations.append(
            {
                "field": "final_action_label",
                "value": context.final_action_label,
                "source": "decision_snapshot",
            }
        )
    if context.hard_filter_decision is not None:
        citations.append(
            {
                "field": "hard_filter_decision",
                "source": "hard_filter_gate",
            }
        )
    citations.append(
        {
            "field": "option_data_status",
            "value": context.option_data_status,
            "source": "manual_option_snapshot"
            if context.has_manual_snapshot
            else "none",
        }
    )
    if context.missing_option_fields:
        citations.append(
            {
                "field": "missing_option_fields",
                "value": context.missing_option_fields,
                "source": "manual_option_parser",
            }
        )
    if context.earnings is not None:
        citations.append({"field": "earnings_risk", "source": "earnings_risk_snapshot"})
    if context.iv is not None:
        citations.append({"field": "iv_risk", "source": "iv_risk_snapshot"})
    if context.similar_cases:
        citations.append(
            {
                "field": "similar_cases",
                "value": len(context.similar_cases),
                "source": "case_memory",
            }
        )
    return citations


__all__ = ["build_citations", "retrieve_sources"]
