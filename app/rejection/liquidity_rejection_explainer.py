"""Phase 23, step 23.9 — Liquidity rejection explainer.

Spread + open-interest based option failures from Phase 15 / 20:

* ``SPREAD_TOO_WIDE``
* ``LOW_OPEN_INTEREST``
"""

from __future__ import annotations

from app.decision.final_decision_builder import FinalDecision
from app.options.option_filters import LOW_OPEN_INTEREST, SPREAD_TOO_WIDE
from app.rejection.breakeven_failure_explainer import ReasonPayload
from app.rejection.rejection_categories import (
    REASON_CATEGORY_OPTION,
    SOURCE_PHASE_HARD_FILTER,
)

_LIQUIDITY_LABELS = {
    SPREAD_TOO_WIDE: (
        "Bid/ask spread is wider than the profile maximum; entering and "
        "exiting the contract is too costly."
    ),
    LOW_OPEN_INTEREST: (
        "Open interest is below the profile minimum; the contract is "
        "illiquid and a fill cannot be relied on."
    ),
}


def explain_liquidity_rejections(decision: FinalDecision) -> list[ReasonPayload]:
    payloads: list[ReasonPayload] = []
    for outcome in decision.hard_filter_decision.outcomes:
        if outcome.category != "option":
            continue
        if outcome.status != "FAIL":
            continue
        label = outcome.label or ""
        if label not in _LIQUIDITY_LABELS:
            continue
        base = _LIQUIDITY_LABELS[label]
        explanation = base
        if outcome.detail:
            explanation = f"{base} ({outcome.detail})"
        payloads.append(
            ReasonPayload(
                reason_label=label,
                reason_category=REASON_CATEGORY_OPTION,
                source_phase=SOURCE_PHASE_HARD_FILTER,
                explanation=explanation,
                context={"value": outcome.value, "filter_name": outcome.name},
            )
        )
    return payloads


__all__ = ["explain_liquidity_rejections"]
