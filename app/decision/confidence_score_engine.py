"""Phase 21, step 21.8 — Confidence score engine.

Combines the per-domain inputs (data sufficiency, hard-filter PASS rate,
event risk, memory risk) into a single 0-100 confidence value and a
``ConfidenceBreakdown`` so the engine remains transparent.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.data_quality.data_sufficiency_gate import (
    GateDecision as SufficiencyDecision,
)
from app.decision.confidence_breakdown import (
    ConfidenceBreakdown,
    build_confidence_breakdown,
)
from app.decision.decision_labels import (
    RISK_HIGH,
    RISK_LOW,
    RISK_MEDIUM,
    RISK_UNKNOWN,
)
from app.decision.event_risk_decision import EventRiskDecision
from app.decision.memory_risk_decision import MemoryRiskDecision
from app.hard_filter.hard_filter_gate import HardFilterDecision
from app.options.option_filters import FAIL, PASS, WARN


@dataclass(frozen=True)
class ConfidenceScore:
    score: float
    breakdown: ConfidenceBreakdown

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": round(self.score, 2),
            "breakdown": self.breakdown.to_dict(),
        }


def compute_confidence_score(
    *,
    sufficiency: SufficiencyDecision,
    hard_filter: HardFilterDecision,
    event_risk: EventRiskDecision,
    memory_risk: MemoryRiskDecision,
) -> ConfidenceScore:
    """0-100 confidence in the decision.

    Components:

    * sufficiency_completeness -- fewer blocking/non-blocking/reducer labels = higher
    * hard_filter_pass_rate    -- PASS share of stock-side hard filters
    * regime_warnings_inverse  -- fewer warnings = higher
    * event_risk_inverse       -- LOW = 100, MEDIUM = 50, HIGH = 0
    * memory_risk_inverse      -- LOW = 100, MEDIUM = 50, HIGH = 0
    """
    component_scores = {
        "sufficiency_completeness": _sufficiency_score(sufficiency),
        "hard_filter_pass_rate": _hard_filter_pass_rate(hard_filter),
        "regime_warnings_inverse": _warnings_inverse(hard_filter),
        "event_risk_inverse": _inverse_risk(event_risk.risk_level),
        "memory_risk_inverse": _inverse_risk(memory_risk.risk_level),
    }
    weights = {
        "sufficiency_completeness": 0.30,
        "hard_filter_pass_rate": 0.30,
        "regime_warnings_inverse": 0.10,
        "event_risk_inverse": 0.20,
        "memory_risk_inverse": 0.10,
    }
    breakdown = build_confidence_breakdown(component_scores, weights)
    return ConfidenceScore(score=breakdown.total, breakdown=breakdown)


def _sufficiency_score(sufficiency: SufficiencyDecision) -> float:
    blocks = len(sufficiency.blocking_labels or [])
    non_blocks = len(sufficiency.non_blocking_labels or [])
    reducers = len(sufficiency.confidence_reducers or [])

    if blocks > 0:
        return 0.0
    # Each non-blocking warning costs 10 points, each reducer 5 (cap floor 0).
    return max(0.0, 100.0 - (non_blocks * 10.0) - (reducers * 5.0))


def _hard_filter_pass_rate(hard_filter: HardFilterDecision) -> float:
    stock_outcomes = [o for o in hard_filter.outcomes if o.category == "stock"]
    ran = [o for o in stock_outcomes if o.status in (PASS, FAIL, WARN)]
    if not ran:
        return 50.0
    passes = sum(1 for o in ran if o.status == PASS)
    return (passes / len(ran)) * 100.0


def _warnings_inverse(hard_filter: HardFilterDecision) -> float:
    count = len(hard_filter.warning_labels or [])
    if count == 0:
        return 100.0
    if count == 1:
        return 60.0
    if count == 2:
        return 30.0
    return 0.0


def _inverse_risk(risk_level: str) -> float:
    if risk_level == RISK_LOW:
        return 100.0
    if risk_level == RISK_MEDIUM:
        return 50.0
    if risk_level == RISK_HIGH:
        return 0.0
    if risk_level == RISK_UNKNOWN:
        return 60.0
    return 50.0


__all__ = ["ConfidenceScore", "compute_confidence_score"]
