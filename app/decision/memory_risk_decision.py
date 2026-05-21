"""Phase 21, step 21.5 — Memory-risk decision.

Memory is a forward-looking input: the persistent case-memory and vector-
memory stores arrive in Phase 23+. The Phase 21 decision layer accepts
whatever memory rows the caller can supply (today: empty) and produces a
LOW / MEDIUM / HIGH / UNKNOWN bucket with a clear "no memory yet" factor
so dashboards never see a hardcoded "LOW" that pretends memory is rich.

This module is deliberately small. The bucketing logic will expand once
the memory store exists; today it primarily protects the decision trace
from silently dropping the memory step.
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


@dataclass(frozen=True)
class MemoryRiskInputs:
    """Inputs the memory decision will consume once memory lands.

    * ``similar_case_count``: how many comparable historical cases exist.
    * ``negative_outcome_share``: fraction of those cases that were
      negative outcomes (0.0 - 1.0). ``None`` when no data.
    * ``memory_data_available``: whether the memory store is wired and
      reachable at all (False during Phase 21 because the store does not
      yet exist).
    """

    similar_case_count: int = 0
    negative_outcome_share: float | None = None
    memory_data_available: bool = False


@dataclass(frozen=True)
class MemoryRiskDecision:
    risk_level: str
    factors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"risk_level": self.risk_level, "factors": list(self.factors)}


def decide_memory_risk(inputs: MemoryRiskInputs) -> MemoryRiskDecision:
    if not inputs.memory_data_available or inputs.similar_case_count == 0:
        return MemoryRiskDecision(
            risk_level=RISK_UNKNOWN,
            factors=[
                "No memory rows available yet (memory store arrives in a "
                "later phase)."
            ],
        )

    share = inputs.negative_outcome_share
    if share is None:
        return MemoryRiskDecision(
            risk_level=RISK_UNKNOWN,
            factors=[
                f"{inputs.similar_case_count} similar cases found, but no "
                "negative-outcome share computed."
            ],
        )

    if share >= 0.6:
        return MemoryRiskDecision(
            risk_level=RISK_HIGH,
            factors=[
                f"{share * 100:.0f}% of {inputs.similar_case_count} "
                "comparable cases ended in negative outcomes."
            ],
        )
    if share >= 0.3:
        return MemoryRiskDecision(
            risk_level=RISK_MEDIUM,
            factors=[
                f"{share * 100:.0f}% of {inputs.similar_case_count} "
                "comparable cases were negative; treat with caution."
            ],
        )
    return MemoryRiskDecision(
        risk_level=RISK_LOW,
        factors=[
            f"{share * 100:.0f}% of {inputs.similar_case_count} "
            "comparable cases were negative; track record is constructive."
        ],
    )


__all__ = ["MemoryRiskDecision", "MemoryRiskInputs", "decide_memory_risk"]
