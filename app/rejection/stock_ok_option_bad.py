"""Phase 23, step 23.4 — Detect "stock thesis OK, option contract bad".

The rule (verbatim from the Phase 23 outline):

    Bad pasted option data can reject **only** the option expression.

So when the Phase 21 final label is ``STOCK_OK_OPTION_BAD`` (i.e. the
user pasted an option that failed Phase 20 option filters, but the
stock thesis itself is ready), the rejection layer marks this as an
**option-only** rejection. The stock side is not classified as a hard
rejection; the candidate is still researchable as a stock-only idea.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.decision.decision_labels import STOCK_OK_OPTION_BAD
from app.decision.final_decision_builder import FinalDecision


@dataclass(frozen=True)
class StockOkOptionBadResult:
    matched: bool
    option_blocking_labels: list[str]
    rationale: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "matched": self.matched,
            "option_blocking_labels": list(self.option_blocking_labels),
            "rationale": self.rationale,
        }


def detect_stock_ok_option_bad(decision: FinalDecision) -> StockOkOptionBadResult:
    if decision.final_label != STOCK_OK_OPTION_BAD:
        return StockOkOptionBadResult(
            matched=False,
            option_blocking_labels=[],
            rationale="Not the stock-OK / option-bad final label.",
        )

    option_blocking = list(decision.hard_filter_decision.option_blocking_labels or [])
    rationale = (
        "Stock thesis passes hard filters; one or more option-side hard filters "
        "failed. The rejection applies only to the option expression."
    )
    return StockOkOptionBadResult(
        matched=True,
        option_blocking_labels=option_blocking,
        rationale=rationale,
    )


__all__ = ["StockOkOptionBadResult", "detect_stock_ok_option_bad"]
