"""Phase 23, step 23.8 — IV / earnings rejection explainer.

Produces structured ``ReasonPayload`` entries for:

* ``IV_TOO_HIGH``                          (option-side)
* ``EARNINGS_INSIDE_WINDOW``               (stock-side warning/block)
* ``EARNINGS_BEFORE_OPTION_EXPIRATION``    (stock-side hard fail)

The explainer reads only the Phase 20 hard-filter outcomes; nothing is
re-evaluated.
"""

from __future__ import annotations

from app.decision.final_decision_builder import FinalDecision
from app.hard_filter.hard_filter_gate import (
    EARNINGS_BEFORE_OPTION_EXPIRATION,
    EARNINGS_INSIDE_WINDOW,
)
from app.options.iv_analysis import IV_TOO_HIGH
from app.rejection.breakeven_failure_explainer import ReasonPayload
from app.rejection.rejection_categories import (
    REASON_CATEGORY_EVENT,
    REASON_CATEGORY_OPTION,
    SOURCE_PHASE_HARD_FILTER,
)

_EVENT_LABELS = {
    IV_TOO_HIGH: (REASON_CATEGORY_OPTION,
        "Implied volatility is at or above the profile's reject threshold; "
        "the contract is too expensive on a vol basis."),
    EARNINGS_INSIDE_WINDOW: (REASON_CATEGORY_EVENT,
        "Earnings event is inside the configured risk window; the candidate "
        "may re-arm once the report clears."),
    EARNINGS_BEFORE_OPTION_EXPIRATION: (REASON_CATEGORY_EVENT,
        "Earnings event falls before the option expiration date; this is a "
        "non-bypassable hard fail. Choose a longer expiration to recover."),
}


def explain_iv_earnings_rejections(decision: FinalDecision) -> list[ReasonPayload]:
    payloads: list[ReasonPayload] = []
    for outcome in decision.hard_filter_decision.outcomes:
        # Status FAIL or WARN -- earnings inside window can land in either
        # column depending on the ``hard_filter_earnings_inside_window_blocks``
        # setting. The rejection layer reports it either way.
        if outcome.status not in {"FAIL", "WARN"}:
            continue
        label = outcome.label or ""
        if label not in _EVENT_LABELS:
            continue
        category, base = _EVENT_LABELS[label]
        explanation = base
        if outcome.detail:
            explanation = f"{base} ({outcome.detail})"
        payloads.append(
            ReasonPayload(
                reason_label=label,
                reason_category=category,
                source_phase=SOURCE_PHASE_HARD_FILTER,
                explanation=explanation,
                context={
                    "value": outcome.value,
                    "filter_name": outcome.name,
                    "status": outcome.status,
                },
            )
        )
    return payloads


__all__ = ["explain_iv_earnings_rejections"]
