"""Phase 21, step 21.11 — Decision trace builder.

Records each decision step into a list of ``{step, status, summary}``
entries. The trace is a debug / dashboard surface: it explains *why* a
final label was produced without re-running the upstream logic.
"""

from __future__ import annotations

from typing import Any

from app.data_quality.data_sufficiency_gate import GateDecision as SufficiencyDecision
from app.decision.action_label_classifier import ActionLabel
from app.decision.event_risk_decision import EventRiskDecision
from app.decision.instrument_scope_classifier import InstrumentScope
from app.decision.memory_risk_decision import MemoryRiskDecision
from app.decision.option_expression_decision import OptionExpressionDecision
from app.decision.stock_thesis_decision import StockThesisDecision
from app.hard_filter.hard_filter_gate import HardFilterDecision


def build_decision_trace(
    *,
    sufficiency: SufficiencyDecision,
    hard_filter: HardFilterDecision,
    thesis: StockThesisDecision,
    option_expression: OptionExpressionDecision,
    scope: InstrumentScope,
    event_risk: EventRiskDecision,
    memory_risk: MemoryRiskDecision,
    final_action: ActionLabel,
) -> list[dict[str, Any]]:
    return [
        {
            "step": "data_sufficiency_gate",
            "status": sufficiency.stock_decision_status,
            "summary": _summarize_sufficiency(sufficiency),
        },
        {
            "step": "hard_filter_gate",
            "status": hard_filter.overall_decision,
            "summary": _summarize_hard_filter(hard_filter),
        },
        {
            "step": "stock_thesis_decision",
            "status": thesis.thesis_label,
            "summary": "; ".join(thesis.rationale) or "no rationale recorded",
        },
        {
            "step": "option_expression_decision",
            "status": option_expression.expression_label,
            "summary": "; ".join(option_expression.rationale) or "no rationale recorded",
        },
        {
            "step": "instrument_scope_classifier",
            "status": scope.scope,
            "summary": "; ".join(scope.rationale) or "no rationale recorded",
        },
        {
            "step": "event_risk_decision",
            "status": event_risk.risk_level,
            "summary": "; ".join(event_risk.factors) or "no factors",
        },
        {
            "step": "memory_risk_decision",
            "status": memory_risk.risk_level,
            "summary": "; ".join(memory_risk.factors) or "no factors",
        },
        {
            "step": "action_label_classifier",
            "status": final_action.final_label,
            "summary": final_action.rationale,
        },
    ]


def _summarize_sufficiency(decision: SufficiencyDecision) -> str:
    parts = []
    if decision.blocking_labels:
        parts.append("blocking=" + ",".join(sorted(set(decision.blocking_labels))))
    if decision.non_blocking_labels:
        parts.append(
            "non_blocking=" + ",".join(sorted(set(decision.non_blocking_labels)))
        )
    if decision.confidence_reducers:
        parts.append(
            "reducers=" + ",".join(sorted(set(decision.confidence_reducers)))
        )
    if not parts:
        return "all sufficiency checks pass"
    return "; ".join(parts)


def _summarize_hard_filter(decision: HardFilterDecision) -> str:
    parts = []
    if decision.stock_blocking_labels:
        parts.append(
            "stock_block=" + ",".join(sorted(set(decision.stock_blocking_labels)))
        )
    if decision.option_blocking_labels:
        parts.append(
            "option_block=" + ",".join(sorted(set(decision.option_blocking_labels)))
        )
    if decision.warning_labels:
        parts.append("warn=" + ",".join(sorted(set(decision.warning_labels))))
    if not parts:
        return "all hard filters pass"
    return "; ".join(parts)


__all__ = ["build_decision_trace"]
