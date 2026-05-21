"""Phase 22, step 22.1 — Suggested action summary.

A one-sentence, deterministic summary of the next action. Reads only
the Phase 21 final decision (label + key scalars) so the summary is
stable across reruns and doesn't depend on AI providers.
"""

from __future__ import annotations

from app.decision.decision_labels import (
    INSUFFICIENT_PRICE_HISTORY,
    NO_TRADE,
    OPTION_DATA_NOT_AVAILABLE,
    READY_TO_RESEARCH_STOCK_ONLY,
    READY_TO_RESEARCH_WITH_OPTION,
    STOCK_OK_OPTION_BAD,
    WAIT_FOR_ENTRY_STOCK_ONLY,
    WATCH_STOCK_ONLY,
)
from app.decision.final_decision_builder import FinalDecision


def build_suggested_action_summary(decision: FinalDecision) -> str:
    symbol = decision.symbol or "this symbol"
    label = decision.final_label

    if label == READY_TO_RESEARCH_STOCK_ONLY:
        return (
            f"Research {symbol} as a stock-only candidate; option data is "
            "not required and not requested."
        )

    if label == READY_TO_RESEARCH_WITH_OPTION:
        return (
            f"Research {symbol} with the supplied option contract; both "
            "stock and option pass hard filters."
        )

    if label == STOCK_OK_OPTION_BAD:
        return (
            f"Research the stock thesis on {symbol}; the supplied option "
            "contract fails hard filters, so do not use it as the expression."
        )

    if label == OPTION_DATA_NOT_AVAILABLE:
        return (
            f"Stock thesis on {symbol} is ready, but option analysis was "
            "requested without option data; paste a contract to continue."
        )

    if label == WAIT_FOR_ENTRY_STOCK_ONLY:
        return (
            f"Wait for {symbol} to come back into the entry zone before "
            "starting the research checklist."
        )

    if label == WATCH_STOCK_ONLY:
        return (
            f"Watch {symbol}; setup is allowed but warnings are present "
            "and the thesis is not yet ready for execution."
        )

    if label == NO_TRADE:
        return (
            f"Do not trade {symbol}; one or more non-negotiable rules "
            "blocked the stock thesis."
        )

    if label == INSUFFICIENT_PRICE_HISTORY:
        return (
            f"Cannot evaluate {symbol} yet; insufficient price history "
            "for setup math."
        )

    # Defensive fallback -- never reached when the upstream label set stays
    # in sync.
    return f"No action defined for {symbol} (label '{label}')."


__all__ = ["build_suggested_action_summary"]
