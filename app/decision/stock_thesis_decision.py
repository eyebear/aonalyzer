"""Phase 21, step 21.1 — Stock thesis decision.

Judges the stock thesis status from the Phase 19 sufficiency gate, the
Phase 20 hard filter gate, and the persisted stock setup. Emits an
**internal** label (``READY_TO_RESEARCH`` / ``WATCH`` / ``WAIT_FOR_ENTRY``
/ ``NO_TRADE`` / ``INSUFFICIENT_PRICE_HISTORY``) which the action
classifier then combines with the instrument scope.

Inputs come from already-computed gate decisions. This module does not
re-load anything from the database; the orchestrator wires the inputs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.data_quality.data_sufficiency_gate import (
    STOCK_DECISION_ALLOWED,
)
from app.data_quality.data_sufficiency_gate import (
    GateDecision as SufficiencyDecision,
)
from app.data_quality.data_sufficiency_labels import DataSufficiencyLabel
from app.decision.decision_labels import (
    THESIS_INSUFFICIENT_PRICE_HISTORY,
    THESIS_NO_TRADE,
    THESIS_READY_TO_RESEARCH,
    THESIS_WAIT_FOR_ENTRY,
    THESIS_WATCH,
)
from app.hard_filter.hard_filter_gate import (
    DECISION_ALLOWED as HARD_FILTER_ALLOWED,
)
from app.hard_filter.hard_filter_gate import (
    HardFilterDecision,
)


@dataclass(frozen=True)
class StockThesisInputs:
    """Lightweight context the decision needs beyond the two gate outputs."""

    direction: str | None = None  # LONG / SHORT / UNDEFINED
    current_close: float | None = None
    entry_zone_low: float | None = None
    entry_zone_high: float | None = None


@dataclass(frozen=True)
class StockThesisDecision:
    thesis_label: str
    rationale: list[str] = field(default_factory=list)
    inside_entry_zone: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "thesis_label": self.thesis_label,
            "rationale": list(self.rationale),
            "inside_entry_zone": self.inside_entry_zone,
        }


def decide_stock_thesis(
    sufficiency: SufficiencyDecision,
    hard_filter: HardFilterDecision,
    inputs: StockThesisInputs | None = None,
) -> StockThesisDecision:
    inputs = inputs or StockThesisInputs()
    rationale: list[str] = []

    # --- Step 1: INSUFFICIENT_PRICE_HISTORY beats everything ----------------
    blocking = set(sufficiency.blocking_labels or [])
    if DataSufficiencyLabel.INSUFFICIENT_PRICE_HISTORY.value in blocking:
        rationale.append(
            "Phase 19 reports insufficient price history; setup math cannot run."
        )
        return StockThesisDecision(
            thesis_label=THESIS_INSUFFICIENT_PRICE_HISTORY,
            rationale=rationale,
        )

    # --- Step 2: any other sufficiency block, or any hard-filter block ------
    if sufficiency.stock_decision_status != STOCK_DECISION_ALLOWED:
        rationale.append(
            "Phase 19 sufficiency gate blocks stock decision: "
            + ", ".join(sorted(blocking))
        )
        return StockThesisDecision(thesis_label=THESIS_NO_TRADE, rationale=rationale)

    if hard_filter.overall_decision != HARD_FILTER_ALLOWED:
        rationale.append(
            "Phase 20 hard filter gate blocks stock decision: "
            + ", ".join(sorted(set(hard_filter.stock_blocking_labels)))
        )
        return StockThesisDecision(thesis_label=THESIS_NO_TRADE, rationale=rationale)

    # --- Step 3: distinguish READY / WATCH / WAIT_FOR_ENTRY ----------------
    inside_zone = _inside_entry_zone(inputs)
    if inside_zone is False:
        rationale.append(
            "Current close is outside the entry zone; wait for price to come "
            "back into range."
        )
        return StockThesisDecision(
            thesis_label=THESIS_WAIT_FOR_ENTRY,
            rationale=rationale,
            inside_entry_zone=False,
        )

    if hard_filter.warning_labels:
        rationale.append(
            "Stock thesis is allowed but the hard filter raised warnings: "
            + ", ".join(sorted(set(hard_filter.warning_labels)))
        )
        return StockThesisDecision(
            thesis_label=THESIS_WATCH,
            rationale=rationale,
            inside_entry_zone=inside_zone,
        )

    rationale.append(
        "Phase 19 sufficiency allows, Phase 20 hard filters allow, "
        "and price is inside the entry zone."
    )
    return StockThesisDecision(
        thesis_label=THESIS_READY_TO_RESEARCH,
        rationale=rationale,
        inside_entry_zone=inside_zone,
    )


def _inside_entry_zone(inputs: StockThesisInputs) -> bool | None:
    """Return True/False if we can compare price to the entry zone; ``None``
    when one or both bounds are missing (treated as "no opinion")."""
    if inputs.current_close is None:
        return None
    if inputs.entry_zone_low is None or inputs.entry_zone_high is None:
        return None
    low = min(inputs.entry_zone_low, inputs.entry_zone_high)
    high = max(inputs.entry_zone_low, inputs.entry_zone_high)
    return low <= inputs.current_close <= high


__all__ = ["StockThesisDecision", "StockThesisInputs", "decide_stock_thesis"]
