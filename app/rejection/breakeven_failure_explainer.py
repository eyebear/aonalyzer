"""Phase 23, step 23.7 — Breakeven failure explainer.

Produces structured ``RejectionReason``-shaped payloads for the two
breakeven-related option failures from Phase 15 / 20:

* ``BREAKEVEN_TOO_FAR``
* ``TARGET_BELOW_BREAKEVEN``
* ``TARGET_MARGIN_TOO_THIN``

Reads only the hard-filter outcomes; never re-derives breakeven math.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.decision.final_decision_builder import FinalDecision
from app.options.target_breakeven import (
    BREAKEVEN_TOO_FAR,
    TARGET_BELOW_BREAKEVEN,
    TARGET_MARGIN_TOO_THIN,
)
from app.rejection.rejection_categories import (
    REASON_CATEGORY_OPTION,
    SOURCE_PHASE_HARD_FILTER,
)

_BREAKEVEN_LABELS = frozenset(
    {BREAKEVEN_TOO_FAR, TARGET_BELOW_BREAKEVEN, TARGET_MARGIN_TOO_THIN}
)


@dataclass(frozen=True)
class ReasonPayload:
    reason_label: str
    reason_category: str
    source_phase: str
    explanation: str
    context: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "reason_label": self.reason_label,
            "reason_category": self.reason_category,
            "source_phase": self.source_phase,
            "explanation": self.explanation,
            "context": dict(self.context),
        }


def explain_breakeven_failures(decision: FinalDecision) -> list[ReasonPayload]:
    """Return one reason per breakeven-related FAIL outcome, in order."""
    payloads: list[ReasonPayload] = []
    for outcome in decision.hard_filter_decision.outcomes:
        if outcome.category != "option":
            continue
        if outcome.status != "FAIL":
            continue
        label = outcome.label or ""
        if label not in _BREAKEVEN_LABELS:
            continue
        payloads.append(
            ReasonPayload(
                reason_label=label,
                reason_category=REASON_CATEGORY_OPTION,
                source_phase=SOURCE_PHASE_HARD_FILTER,
                explanation=_explanation_for(label, outcome.detail or ""),
                context={"value": outcome.value, "filter_name": outcome.name},
            )
        )
    return payloads


def _explanation_for(label: str, detail: str) -> str:
    base = {
        BREAKEVEN_TOO_FAR: (
            "Breakeven sits too far from the current underlying price; the "
            "contract requires a larger move than the setup supports."
        ),
        TARGET_BELOW_BREAKEVEN: (
            "The stock target lands on the unprofitable side of breakeven; "
            "even hitting target would not deliver positive option payoff."
        ),
        TARGET_MARGIN_TOO_THIN: (
            "Stock target clears breakeven by less than the profile minimum; "
            "the option does not offer enough margin of safety."
        ),
    }.get(label, "Breakeven-related option failure.")
    if detail:
        return f"{base} ({detail})"
    return base


__all__ = ["ReasonPayload", "explain_breakeven_failures"]
