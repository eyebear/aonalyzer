"""Phase 23, step 23.5 — Detect "stock thesis OK, option data missing".

The rule (verbatim from the Phase 23 outline):

    Missing option data is **not** a rejection.

This detector exists so the dashboard can distinguish "stock-only ready"
from "stock-ready but option was requested and absent" -- but in neither
case do we write a rejected_candidates row. The returned ``matched``
flag is purely descriptive; the classifier consumes it only to *avoid*
classifying these states as rejections.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.decision.decision_labels import (
    OPTION_DATA_NOT_AVAILABLE,
    READY_TO_RESEARCH_STOCK_ONLY,
)
from app.decision.final_decision_builder import FinalDecision


@dataclass(frozen=True)
class StockOkOptionMissingResult:
    matched: bool
    option_requested: bool
    is_rejection: bool  # always False -- preserved as an explicit invariant
    rationale: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "matched": self.matched,
            "option_requested": self.option_requested,
            "is_rejection": self.is_rejection,
            "rationale": self.rationale,
        }


def detect_stock_ok_option_missing(decision: FinalDecision) -> StockOkOptionMissingResult:
    final = decision.final_label
    option_requested = bool(decision.instrument_scope.option_data_requested)

    if final == OPTION_DATA_NOT_AVAILABLE:
        return StockOkOptionMissingResult(
            matched=True,
            option_requested=True,
            is_rejection=False,
            rationale=(
                "Option analysis was requested but no option data is available; "
                "the stock thesis is still ready. Missing option data is not "
                "treated as a rejection."
            ),
        )

    if final == READY_TO_RESEARCH_STOCK_ONLY:
        # Stock-only ready; option not requested. Not a rejection, not the
        # "missing option" surface either, but the detector returns matched=False
        # rather than raising so the classifier can route deterministically.
        return StockOkOptionMissingResult(
            matched=False,
            option_requested=option_requested,
            is_rejection=False,
            rationale=(
                "Stock-only opportunity; option data was not requested. Not a "
                "rejection."
            ),
        )

    return StockOkOptionMissingResult(
        matched=False,
        option_requested=option_requested,
        is_rejection=False,
        rationale="Not the stock-OK / option-missing state.",
    )


__all__ = ["StockOkOptionMissingResult", "detect_stock_ok_option_missing"]
