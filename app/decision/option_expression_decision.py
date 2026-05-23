"""Phase 21, step 21.2 — Option expression decision.

Judges the option expression **only when option data exists**. When no
option data was supplied, the decision is ``OPTION_NOT_EVALUATED`` and
nothing about the stock decision is affected -- this preserves the
Phase 19/20 invariant that missing option data is never a stock
rejection.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.decision.decision_labels import (
    OPTION_EXPR_BAD,
    OPTION_EXPR_NOT_EVALUATED,
    OPTION_EXPR_OK,
)
from app.hard_filter.hard_filter_gate import (
    OPTION_DECISION_ALLOWED,
    OPTION_DECISION_BLOCKED,
    HardFilterDecision,
)


@dataclass(frozen=True)
class OptionExpressionDecision:
    expression_label: str
    blocking_labels: list[str] = field(default_factory=list)
    rationale: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "expression_label": self.expression_label,
            "blocking_labels": list(self.blocking_labels),
            "rationale": list(self.rationale),
        }


def decide_option_expression(
    hard_filter: HardFilterDecision,
) -> OptionExpressionDecision:
    rationale: list[str] = []

    if hard_filter.option_decision == OPTION_DECISION_ALLOWED:
        rationale.append("Option passes all applicable Phase 20 hard filters.")
        return OptionExpressionDecision(
            expression_label=OPTION_EXPR_OK,
            rationale=rationale,
        )

    if hard_filter.option_decision == OPTION_DECISION_BLOCKED:
        rationale.append(
            "Option fails one or more Phase 20 hard filters: "
            + ", ".join(sorted(set(hard_filter.option_blocking_labels)))
        )
        return OptionExpressionDecision(
            expression_label=OPTION_EXPR_BAD,
            blocking_labels=list(hard_filter.option_blocking_labels),
            rationale=rationale,
        )

    rationale.append(
        "No option data was supplied; option expression is not evaluated."
    )
    return OptionExpressionDecision(
        expression_label=OPTION_EXPR_NOT_EVALUATED,
        rationale=rationale,
    )


__all__ = ["OptionExpressionDecision", "decide_option_expression"]
