"""Phase 28, step 28.3 — ticker brief builder.

Pure assembler: takes a ``BriefInputs`` bundle (already gathered by the
service from existing decision / action / event / risk records) and composes
the ordered list of brief sections plus the top-level summary fields. It does
NOT recompute decisions — it only arranges what was passed in.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from app.brief.brief_sections import (
    build_confidence_section,
    build_current_action_section,
    build_decision_trace_section,
    build_earnings_iv_section,
    build_manual_option_reminder_section,
    build_memory_section,
    build_news_events_section,
    build_option_expression_section,
    build_stock_thesis_section,
    build_version_section,
)


@dataclass
class BriefInputs:
    symbol: str
    snapshot_date: date
    final_action_label: str
    suggested_action_summary: str | None = None
    priority_score: float | None = None
    confidence_score: float | None = None
    lifecycle_state: str | None = None
    instrument_scope: str | None = None

    stock_thesis: dict[str, Any] | None = None
    option_expression: dict[str, Any] | None = None
    option_contract_criteria: dict[str, Any] | None = None
    has_manual_snapshot: bool = False
    manual_option_input_needed: bool = False
    missing_fields: list[str] = field(default_factory=list)

    earnings: dict[str, Any] | None = None
    iv: dict[str, Any] | None = None
    events: list[dict[str, Any]] = field(default_factory=list)
    similar_cases: list[dict[str, Any]] = field(default_factory=list)

    decision_trace: list[dict[str, Any]] = field(default_factory=list)
    confidence_breakdown: dict[str, Any] | None = None
    version_stamp: dict[str, Any] = field(default_factory=dict)

    profile_name: str | None = None
    profile_version: str | None = None


@dataclass
class TickerBriefResult:
    symbol: str
    snapshot_date: date
    final_action_label: str
    instrument_scope: str | None
    lifecycle_state: str | None
    option_expression_status: str | None
    priority_score: float | None
    confidence_score: float | None
    sections: list[dict[str, Any]]
    version_stamp: dict[str, Any]
    profile_name: str | None
    profile_version: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "snapshot_date": self.snapshot_date.isoformat(),
            "final_action_label": self.final_action_label,
            "instrument_scope": self.instrument_scope,
            "lifecycle_state": self.lifecycle_state,
            "option_expression_status": self.option_expression_status,
            "priority_score": self.priority_score,
            "confidence_score": self.confidence_score,
            "sections": list(self.sections),
            "version_stamp": dict(self.version_stamp),
            "profile_name": self.profile_name,
            "profile_version": self.profile_version,
        }


def build_ticker_brief(inputs: BriefInputs) -> TickerBriefResult:
    option_section = build_option_expression_section(
        option_expression=inputs.option_expression,
        has_manual_snapshot=inputs.has_manual_snapshot,
        option_contract_criteria=inputs.option_contract_criteria,
    )

    sections = [
        build_current_action_section(
            final_action_label=inputs.final_action_label,
            suggested_action_summary=inputs.suggested_action_summary,
            priority_score=inputs.priority_score,
            confidence_score=inputs.confidence_score,
            lifecycle_state=inputs.lifecycle_state,
            instrument_scope=inputs.instrument_scope,
        ),
        build_stock_thesis_section(inputs.stock_thesis),
        option_section,
        build_manual_option_reminder_section(
            manual_option_input_needed=inputs.manual_option_input_needed,
            has_manual_snapshot=inputs.has_manual_snapshot,
            missing_fields=inputs.missing_fields,
            option_contract_criteria=inputs.option_contract_criteria,
        ),
        build_earnings_iv_section(earnings=inputs.earnings, iv=inputs.iv),
        build_news_events_section(inputs.events),
        build_memory_section(inputs.similar_cases),
        build_decision_trace_section(inputs.decision_trace),
        build_confidence_section(
            confidence_score=inputs.confidence_score,
            breakdown=inputs.confidence_breakdown,
        ),
        build_version_section(inputs.version_stamp),
    ]

    return TickerBriefResult(
        symbol=inputs.symbol,
        snapshot_date=inputs.snapshot_date,
        final_action_label=inputs.final_action_label,
        instrument_scope=inputs.instrument_scope,
        lifecycle_state=inputs.lifecycle_state,
        option_expression_status=option_section.get("option_expression_status"),
        priority_score=inputs.priority_score,
        confidence_score=inputs.confidence_score,
        sections=sections,
        version_stamp=inputs.version_stamp,
        profile_name=inputs.profile_name,
        profile_version=inputs.profile_version,
    )


__all__ = ["BriefInputs", "TickerBriefResult", "build_ticker_brief"]
