"""Phase 21, step 21.3 — Instrument scope classifier.

Outputs one of ``STOCK_ONLY`` / ``OPTION_AVAILABLE`` / ``OPTION_REJECTED``
based on:

* whether option data was supplied to the decision (the
  ``option_data_requested`` flag carried through from Phase 19),
* whether the Phase 20 option-side hard filter passed or failed.

This decides the *type* of opportunity the user gets; it does **not**
decide whether a stock can be researched.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.decision.decision_labels import (
    OPTION_EXPR_BAD,
    OPTION_EXPR_NOT_EVALUATED,
    OPTION_EXPR_OK,
    SCOPE_OPTION_AVAILABLE,
    SCOPE_OPTION_REJECTED,
    SCOPE_STOCK_ONLY,
)
from app.decision.option_expression_decision import OptionExpressionDecision


@dataclass(frozen=True)
class InstrumentScope:
    scope: str
    option_data_requested: bool
    rationale: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scope": self.scope,
            "option_data_requested": self.option_data_requested,
            "rationale": list(self.rationale),
        }


def classify_instrument_scope(
    option_expression: OptionExpressionDecision,
    *,
    option_data_requested: bool = False,
) -> InstrumentScope:
    rationale: list[str] = []

    if option_expression.expression_label == OPTION_EXPR_OK:
        rationale.append("Option data supplied and option passed hard filters.")
        return InstrumentScope(
            scope=SCOPE_OPTION_AVAILABLE,
            option_data_requested=option_data_requested,
            rationale=rationale,
        )

    if option_expression.expression_label == OPTION_EXPR_BAD:
        rationale.append("Option data supplied but option failed hard filters.")
        return InstrumentScope(
            scope=SCOPE_OPTION_REJECTED,
            option_data_requested=option_data_requested,
            rationale=rationale,
        )

    # OPTION_EXPR_NOT_EVALUATED -- no option data
    if option_data_requested:
        rationale.append(
            "Option analysis was requested but no option data was supplied; "
            "scope falls back to STOCK_ONLY (the final-label classifier "
            "will surface OPTION_DATA_NOT_AVAILABLE)."
        )
    else:
        rationale.append("No option data was supplied; scope is STOCK_ONLY.")

    return InstrumentScope(
        scope=SCOPE_STOCK_ONLY,
        option_data_requested=option_data_requested,
        rationale=rationale,
    )


__all__ = ["InstrumentScope", "classify_instrument_scope"]
