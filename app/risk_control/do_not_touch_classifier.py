"""Phase 24, step 24.3 — Do-Not-Touch classifier.

Inspects the Phase 20 hard-filter outcomes, the Phase 21 final decision,
the Phase 23 rejection classification, and the Phase 23 rejected-
candidates history to decide whether a symbol should be frozen, and
under which category / severity.

The two non-negotiable rules from the Phase 24 outline:

1. **Missing option data alone does not create Do-Not-Touch.**
   ``OPTION_DATA_NOT_AVAILABLE`` never triggers a freeze here. The
   classifier explicitly tests for that label and returns
   ``decision=NO_FREEZE`` before any other rule fires.
2. **Extreme pasted option risk can create Do-Not-Touch.** When the
   user has supplied option data and Phase 20 reports
   ``IV_TOO_HIGH`` (or a combined liquidity collapse), this classifier
   returns ``EXTREME_OPTION_VOLATILITY`` or
   ``EXTREME_OPTION_LIQUIDITY_RISK``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.decision.decision_labels import OPTION_DATA_NOT_AVAILABLE
from app.decision.final_decision_builder import FinalDecision
from app.hard_filter.hard_filter_gate import EARNINGS_BEFORE_OPTION_EXPIRATION
from app.options.iv_analysis import IV_TOO_HIGH
from app.options.option_filters import LOW_OPEN_INTEREST, SPREAD_TOO_WIDE
from app.rejection.rejection_categories import CATEGORY_HARD_STOCK_REJECTION
from app.rejection.rejection_classifier import RejectionClassification
from app.rejection.rejection_models import RejectedCandidate
from app.risk_control.do_not_touch_categories import (
    DEFAULT_REPEATED_REJECTIONS_THRESHOLD,
    DEFAULT_REPEATED_REJECTIONS_WINDOW_DAYS,
    FREEZE_CATEGORY_EARNINGS_BEFORE_EXPIRATION,
    FREEZE_CATEGORY_EXTREME_OPTION_LIQUIDITY_RISK,
    FREEZE_CATEGORY_EXTREME_OPTION_VOLATILITY,
    FREEZE_CATEGORY_REPEATED_REJECTIONS,
    SEVERITY_HARD_FREEZE,
    SEVERITY_SOFT_FREEZE,
    SOURCE_PHASE_CLASSIFIER,
    TRIGGER_AUTOMATIC,
)


DECISION_FREEZE = "FREEZE"
DECISION_NO_FREEZE = "NO_FREEZE"


@dataclass(frozen=True)
class FreezeRecommendation:
    decision: str  # FREEZE / NO_FREEZE
    category: str | None
    severity: str | None
    reason_summary: str
    source_phase: str = SOURCE_PHASE_CLASSIFIER
    triggered_by: str = TRIGGER_AUTOMATIC
    context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "category": self.category,
            "severity": self.severity,
            "reason_summary": self.reason_summary,
            "source_phase": self.source_phase,
            "triggered_by": self.triggered_by,
            "context": dict(self.context),
        }


def classify_do_not_touch(
    *,
    decision: FinalDecision,
    rejection: RejectionClassification,
    db: Session | None = None,
    symbol: str | None = None,
    repeated_window_days: int = DEFAULT_REPEATED_REJECTIONS_WINDOW_DAYS,
    repeated_threshold: int = DEFAULT_REPEATED_REJECTIONS_THRESHOLD,
) -> FreezeRecommendation:
    """Decide whether the candidate should be put on Do-Not-Touch.

    The classifier never re-runs upstream phases; it inspects the
    decision / rejection outputs and (optionally) queries
    ``rejected_candidates`` to detect repeated rejections.
    """
    # ----- Invariant 1: missing option data alone is never a freeze --------
    if decision.final_label == OPTION_DATA_NOT_AVAILABLE:
        return FreezeRecommendation(
            decision=DECISION_NO_FREEZE,
            category=None,
            severity=None,
            reason_summary=(
                "Stock thesis is ready; option data was requested but is "
                "absent. Missing option data does not create a Do-Not-Touch."
            ),
            context={"final_action_label": decision.final_label},
        )

    outcomes = decision.hard_filter_decision.outcomes or []

    # ----- 1. Earnings before option expiration (always a freeze) ----------
    if _has_outcome(outcomes, label=EARNINGS_BEFORE_OPTION_EXPIRATION, status="FAIL"):
        return FreezeRecommendation(
            decision=DECISION_FREEZE,
            category=FREEZE_CATEGORY_EARNINGS_BEFORE_EXPIRATION,
            severity=SEVERITY_HARD_FREEZE,
            reason_summary=(
                "Earnings event falls before the option expiration date; "
                "freeze the candidate until the earnings risk clears."
            ),
            context={"trigger_label": EARNINGS_BEFORE_OPTION_EXPIRATION},
        )

    # ----- 2. Extreme pasted option risk (Invariant 2) --------------------
    # Only fires when option data was supplied -- the hard-filter outcomes
    # are otherwise SKIPPED.
    if _has_outcome(outcomes, label=IV_TOO_HIGH, status="FAIL"):
        return FreezeRecommendation(
            decision=DECISION_FREEZE,
            category=FREEZE_CATEGORY_EXTREME_OPTION_VOLATILITY,
            severity=SEVERITY_HARD_FREEZE,
            reason_summary=(
                "Pasted option contract has IV at or above the reject "
                "threshold; freeze the candidate until volatility cools."
            ),
            context={"trigger_label": IV_TOO_HIGH},
        )

    has_spread = _has_outcome(outcomes, label=SPREAD_TOO_WIDE, status="FAIL")
    has_oi = _has_outcome(outcomes, label=LOW_OPEN_INTEREST, status="FAIL")
    if has_spread and has_oi:
        return FreezeRecommendation(
            decision=DECISION_FREEZE,
            category=FREEZE_CATEGORY_EXTREME_OPTION_LIQUIDITY_RISK,
            severity=SEVERITY_SOFT_FREEZE,
            reason_summary=(
                "Pasted option contract has both an unacceptably wide spread "
                "and very low open interest; the contract is functionally "
                "untradeable. Freeze until liquidity improves."
            ),
            context={"trigger_labels": [SPREAD_TOO_WIDE, LOW_OPEN_INTEREST]},
        )

    # ----- 3. Repeated hard stock rejections in the recent window ---------
    if (
        db is not None
        and symbol is not None
        and rejection.rejection_category == CATEGORY_HARD_STOCK_REJECTION
    ):
        recent = _count_recent_hard_rejections(
            db=db,
            symbol=symbol,
            window_days=repeated_window_days,
        )
        if recent >= repeated_threshold:
            return FreezeRecommendation(
                decision=DECISION_FREEZE,
                category=FREEZE_CATEGORY_REPEATED_REJECTIONS,
                severity=SEVERITY_SOFT_FREEZE,
                reason_summary=(
                    f"Symbol has been hard-rejected {recent} times in the "
                    f"last {repeated_window_days} days; cool down before "
                    "re-evaluating."
                ),
                context={
                    "recent_hard_rejection_count": recent,
                    "window_days": repeated_window_days,
                },
            )

    return FreezeRecommendation(
        decision=DECISION_NO_FREEZE,
        category=None,
        severity=None,
        reason_summary="No Do-Not-Touch condition is currently present.",
        context={"final_action_label": decision.final_label},
    )


def _has_outcome(outcomes, *, label: str, status: str) -> bool:
    for o in outcomes:
        if o.label == label and o.status == status:
            return True
    return False


def _count_recent_hard_rejections(
    *,
    db: Session,
    symbol: str,
    window_days: int,
) -> int:
    from datetime import date, timedelta

    cutoff = date.today() - timedelta(days=window_days)
    try:
        return (
            db.query(RejectedCandidate)
            .filter(RejectedCandidate.symbol == symbol)
            .filter(RejectedCandidate.snapshot_date >= cutoff)
            .filter(
                RejectedCandidate.rejection_category
                == CATEGORY_HARD_STOCK_REJECTION
            )
            .count()
        )
    except SQLAlchemyError:
        return 0


__all__ = [
    "DECISION_FREEZE",
    "DECISION_NO_FREEZE",
    "FreezeRecommendation",
    "classify_do_not_touch",
]
