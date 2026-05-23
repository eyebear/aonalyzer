"""Phase 21, step 21.7 — Priority score engine.

Ranks opportunities **within categories** (READY / WATCH / WAIT_FOR_ENTRY)
on a 0-100 scale. The score is deterministic from the inputs so dashboards
can sort consistently. Lower is worse, 100 is best.

Components (each capped to 0-100, weighted, then summed):

* stock R:R relative to the profile minimum (40 weight)
* setup direction defined (10 weight)
* market regime alignment (15 weight)
* event risk inverse (20 weight)
* memory risk inverse (5 weight)
* hard-filter warnings inverse (10 weight)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.decision.decision_labels import (
    RISK_HIGH,
    RISK_LOW,
    RISK_MEDIUM,
    RISK_UNKNOWN,
)
from app.decision.event_risk_decision import EventRiskDecision
from app.decision.memory_risk_decision import MemoryRiskDecision
from app.hard_filter.hard_filter_gate import REGIME_OPPOSES_SETUP, HardFilterDecision


@dataclass(frozen=True)
class PriorityScore:
    score: float
    components: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": round(self.score, 2),
            "components": {k: round(v, 2) for k, v in self.components.items()},
        }


def compute_priority_score(
    *,
    hard_filter: HardFilterDecision,
    event_risk: EventRiskDecision,
    memory_risk: MemoryRiskDecision,
    setup_direction: str | None,
    profile_minimum_risk_reward: float,
) -> PriorityScore:
    rr_score = _score_rr(hard_filter.stock_risk_reward, profile_minimum_risk_reward)
    direction_score = 100.0 if _is_defined_direction(setup_direction) else 0.0
    regime_score = 100.0 if REGIME_OPPOSES_SETUP not in hard_filter.warning_labels else 25.0
    event_score = _inverse_risk_score(event_risk.risk_level)
    memory_score = _inverse_risk_score(memory_risk.risk_level)
    warnings_score = _warnings_score(len(hard_filter.warning_labels))

    components = {
        "stock_risk_reward": rr_score * 0.40,
        "setup_direction": direction_score * 0.10,
        "regime_alignment": regime_score * 0.15,
        "event_risk": event_score * 0.20,
        "memory_risk": memory_score * 0.05,
        "hard_filter_warnings": warnings_score * 0.10,
    }
    total = sum(components.values())
    return PriorityScore(score=max(0.0, min(100.0, total)), components=components)


def _score_rr(rr: float | None, minimum: float) -> float:
    if rr is None:
        return 0.0
    if minimum <= 0:
        return 100.0
    ratio = float(rr) / float(minimum)
    # ratio 1.0 -> 50, ratio 2.0 -> 100, ratio >=3.0 -> 100; ratio 0 -> 0.
    if ratio <= 0:
        return 0.0
    if ratio >= 2.0:
        return 100.0
    return min(100.0, ratio * 50.0)


def _is_defined_direction(direction: str | None) -> bool:
    if direction is None:
        return False
    cleaned = direction.strip().upper()
    return cleaned in {"LONG", "SHORT"}


def _inverse_risk_score(risk_level: str) -> float:
    if risk_level == RISK_LOW:
        return 100.0
    if risk_level == RISK_MEDIUM:
        return 50.0
    if risk_level == RISK_HIGH:
        return 0.0
    if risk_level == RISK_UNKNOWN:
        return 60.0
    return 50.0


def _warnings_score(count: int) -> float:
    # 0 warnings -> 100, 1 -> 70, 2 -> 40, 3+ -> 0
    if count <= 0:
        return 100.0
    if count == 1:
        return 70.0
    if count == 2:
        return 40.0
    return 0.0


__all__ = ["PriorityScore", "compute_priority_score"]
