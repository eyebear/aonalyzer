"""Phase 23, step 23.6 — "Rejected but interesting" bucket.

Some rejected candidates are worth keeping on a special watch list -- the
stock thesis itself has constructive properties even though hard filters
or temporary conditions are blocking it right now. Concretely:

* Strong R:R (>= profile minimum + a healthy margin) but blocked by a
  regime-style warning that can pass on its own.
* Earnings-inside-window (passes once the earnings event clears).
* Price-too-extended (passes if price pulls back).
* STOCK_OK_OPTION_BAD -- the *option* failed but the stock is still a
  research candidate; record it under the interesting bucket so the
  dashboard can surface re-paste opportunities.

This module never marks a candidate as "interesting" unless it is also
classified as rejected (or as STOCK_OK_OPTION_BAD). Healthy candidates
are never tagged.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.decision.decision_labels import (
    INSUFFICIENT_PRICE_HISTORY,
    NO_TRADE,
    STOCK_OK_OPTION_BAD,
)
from app.decision.final_decision_builder import FinalDecision
from app.hard_filter.hard_filter_gate import (
    EARNINGS_INSIDE_WINDOW,
    PRICE_TOO_EXTENDED,
    REGIME_OPPOSES_SETUP,
    WEAK_STOCK_RISK_REWARD,
)

# When R:R exceeds this multiple of the profile minimum the candidate has a
# meaningful margin and is worth tracking even after a temporary rejection.
_RR_INTERESTING_MULT = 1.5


@dataclass(frozen=True)
class RejectedButInteresting:
    is_interesting: bool
    reasons: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_interesting": self.is_interesting,
            "reasons": list(self.reasons),
        }


def classify_rejected_but_interesting(
    decision: FinalDecision,
    *,
    profile_minimum_risk_reward: float | None = None,
) -> RejectedButInteresting:
    reasons: list[str] = []
    label = decision.final_label

    # Insufficient price history is never "interesting" -- it is a data fix.
    if label == INSUFFICIENT_PRICE_HISTORY:
        return RejectedButInteresting(is_interesting=False, reasons=[])

    # Healthy candidates (READY / WATCH / WAIT / OPTION_DATA_NOT_AVAILABLE)
    # are not rejections -- they don't belong in this bucket.
    if label not in {NO_TRADE, STOCK_OK_OPTION_BAD}:
        return RejectedButInteresting(is_interesting=False, reasons=[])

    hard = decision.hard_filter_decision
    stock_blocks = set(hard.stock_blocking_labels or [])
    warnings = set(hard.warning_labels or [])

    # ``constructive`` reasons make a candidate interesting on their own.
    # ``supplementary`` reasons only add context once at least one
    # constructive signal has fired -- the regime warning alone is not
    # enough, because a genuinely weak setup that simply happens to face
    # an opposing regime is not "interesting".
    constructive: list[str] = []
    supplementary: list[str] = []

    # --- STOCK_OK_OPTION_BAD: always interesting (stock thesis preserved) -
    if label == STOCK_OK_OPTION_BAD:
        constructive.append(
            "Stock thesis passes hard filters; only the supplied option was "
            "rejected. Track for re-paste with a passing contract."
        )

    # --- Strong R:R despite a soft / temporary block ----------------------
    rr = hard.stock_risk_reward
    if rr is not None and profile_minimum_risk_reward is not None:
        threshold = profile_minimum_risk_reward * _RR_INTERESTING_MULT
        if rr >= threshold and label == NO_TRADE:
            # The hard block is something other than R:R itself.
            if WEAK_STOCK_RISK_REWARD not in stock_blocks:
                constructive.append(
                    f"Stock R:R {rr:.2f} is above {threshold:.2f} "
                    f"({_RR_INTERESTING_MULT:.1f}x profile minimum) despite "
                    "the current hard block."
                )

    # --- Temporary, often-fixable blocks ---------------------------------
    if label == NO_TRADE and EARNINGS_INSIDE_WINDOW in (
        stock_blocks | warnings
    ):
        constructive.append(
            "Earnings event is inside the risk window now; the block will "
            "lift once the report clears."
        )
    if label == NO_TRADE and PRICE_TOO_EXTENDED in stock_blocks:
        constructive.append(
            "Price extension is the active hard block; setup may re-arm on a "
            "healthy pullback."
        )

    # --- Supplementary (only included when something constructive fires) --
    if REGIME_OPPOSES_SETUP in warnings:
        supplementary.append(
            "Broad-market regime is opposing the setup; the candidate may "
            "re-arm if the regime turns supportive."
        )

    is_interesting = bool(constructive)
    reasons = constructive + (supplementary if is_interesting else [])

    return RejectedButInteresting(
        is_interesting=is_interesting,
        reasons=reasons,
    )


__all__ = ["RejectedButInteresting", "classify_rejected_but_interesting"]
