"""Phase 23, step 23.3 — Rejection classifier.

Takes a Phase 21 ``FinalDecision`` (already enriched with the Phase 19
sufficiency gate, the Phase 20 hard filter gate, and the Phase 22
action label) and produces a deterministic rejection classification:

* ``rejection_category`` -- HARD_STOCK_REJECTION / STOCK_OK_OPTION_BAD /
  DATA_INSUFFICIENT / NOT_REJECTED.
* ``rejection_severity`` -- HARD_REJECT / OPTION_ONLY_REJECT /
  NOT_EVALUATED / NOT_REJECTED.
* ``is_rejected_but_interesting`` -- bool, with rationale list.

The two invariants:

1. ``OPTION_DATA_NOT_AVAILABLE`` => ``NOT_REJECTED`` (missing option
   data is never a rejection).
2. ``STOCK_OK_OPTION_BAD`` => ``CATEGORY_STOCK_OK_OPTION_BAD`` /
   ``SEVERITY_OPTION_ONLY_REJECT`` -- the stock thesis is preserved as
   researchable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

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
from app.rejection.rejected_but_interesting import (
    RejectedButInteresting,
    classify_rejected_but_interesting,
)
from app.rejection.rejection_categories import (
    CATEGORY_DATA_INSUFFICIENT,
    CATEGORY_HARD_STOCK_REJECTION,
    CATEGORY_NOT_REJECTED,
    CATEGORY_STOCK_OK_OPTION_BAD,
    SEVERITY_HARD_REJECT,
    SEVERITY_NOT_EVALUATED,
    SEVERITY_NOT_REJECTED,
    SEVERITY_OPTION_ONLY_REJECT,
)
from app.rejection.stock_ok_option_bad import (
    StockOkOptionBadResult,
    detect_stock_ok_option_bad,
)
from app.rejection.stock_ok_option_missing import (
    StockOkOptionMissingResult,
    detect_stock_ok_option_missing,
)


@dataclass(frozen=True)
class RejectionClassification:
    final_action_label: str
    rejection_category: str
    rejection_severity: str
    is_rejected: bool
    is_rejected_but_interesting: bool
    interesting_reasons: list[str] = field(default_factory=list)
    summary: str = ""
    stock_ok_option_bad: StockOkOptionBadResult | None = None
    stock_ok_option_missing: StockOkOptionMissingResult | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "final_action_label": self.final_action_label,
            "rejection_category": self.rejection_category,
            "rejection_severity": self.rejection_severity,
            "is_rejected": self.is_rejected,
            "is_rejected_but_interesting": self.is_rejected_but_interesting,
            "interesting_reasons": list(self.interesting_reasons),
            "summary": self.summary,
            "stock_ok_option_bad": (
                self.stock_ok_option_bad.to_dict()
                if self.stock_ok_option_bad is not None
                else None
            ),
            "stock_ok_option_missing": (
                self.stock_ok_option_missing.to_dict()
                if self.stock_ok_option_missing is not None
                else None
            ),
        }


def classify_rejection(
    decision: FinalDecision,
    *,
    profile_minimum_risk_reward: float | None = None,
) -> RejectionClassification:
    label = decision.final_label

    stock_ok_option_bad = detect_stock_ok_option_bad(decision)
    stock_ok_option_missing = detect_stock_ok_option_missing(decision)
    interesting: RejectedButInteresting = classify_rejected_but_interesting(
        decision,
        profile_minimum_risk_reward=profile_minimum_risk_reward,
    )

    category, severity, is_rejected, summary = _classify_buckets(
        label,
        stock_ok_option_bad=stock_ok_option_bad,
        decision=decision,
    )

    return RejectionClassification(
        final_action_label=label,
        rejection_category=category,
        rejection_severity=severity,
        is_rejected=is_rejected,
        is_rejected_but_interesting=interesting.is_interesting,
        interesting_reasons=list(interesting.reasons),
        summary=summary,
        stock_ok_option_bad=stock_ok_option_bad,
        stock_ok_option_missing=stock_ok_option_missing,
    )


def _classify_buckets(
    label: str,
    *,
    stock_ok_option_bad: StockOkOptionBadResult,
    decision: FinalDecision,
) -> tuple[str, str, bool, str]:
    # 1. Missing option data is NEVER a rejection.
    if label == OPTION_DATA_NOT_AVAILABLE:
        return (
            CATEGORY_NOT_REJECTED,
            SEVERITY_NOT_REJECTED,
            False,
            (
                "Stock thesis is ready; option analysis was requested but no "
                "option data is available. Missing option data is not a rejection."
            ),
        )

    # 2. Insufficient price history -- couldn't evaluate, not a rejection
    #    of the stock thesis per se.
    if label == INSUFFICIENT_PRICE_HISTORY:
        return (
            CATEGORY_DATA_INSUFFICIENT,
            SEVERITY_NOT_EVALUATED,
            True,  # still tracked in rejected_candidates for visibility
            (
                "Cannot evaluate the candidate yet; insufficient price history. "
                "Re-evaluate after the next market-data refresh."
            ),
        )

    # 3. STOCK_OK_OPTION_BAD -- option-only rejection.
    if label == STOCK_OK_OPTION_BAD:
        return (
            CATEGORY_STOCK_OK_OPTION_BAD,
            SEVERITY_OPTION_ONLY_REJECT,
            True,
            (
                "Stock thesis is researchable; only the supplied option contract "
                "failed hard filters. Rejection applies to the option expression "
                "only."
            ),
        )

    # 4. NO_TRADE -- hard stock rejection.
    if label == NO_TRADE:
        blocks = ", ".join(
            sorted(set(decision.hard_filter_decision.stock_blocking_labels or []))
        )
        summary = (
            "Stock thesis rejected by the non-negotiable risk filters"
            + (f" ({blocks})" if blocks else "")
            + "."
        )
        return (
            CATEGORY_HARD_STOCK_REJECTION,
            SEVERITY_HARD_REJECT,
            True,
            summary,
        )

    # 5. Healthy states.
    if label in {
        READY_TO_RESEARCH_STOCK_ONLY,
        READY_TO_RESEARCH_WITH_OPTION,
        WATCH_STOCK_ONLY,
        WAIT_FOR_ENTRY_STOCK_ONLY,
    }:
        return (
            CATEGORY_NOT_REJECTED,
            SEVERITY_NOT_REJECTED,
            False,
            f"Candidate is not rejected ({label}).",
        )

    # Defensive fallback -- treated as NOT_REJECTED so an unknown label
    # never silently writes a rejection row.
    return (
        CATEGORY_NOT_REJECTED,
        SEVERITY_NOT_REJECTED,
        False,
        f"Unknown final label '{label}'; treated as not rejected.",
    )


__all__ = ["RejectionClassification", "classify_rejection"]
