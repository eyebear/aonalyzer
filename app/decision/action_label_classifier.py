"""Phase 21, step 21.10 — Final action-label classifier.

Maps the stock-thesis internal label + the instrument scope into one of
the eight final user-facing labels defined in the Phase 21 outline:

* ``READY_TO_RESEARCH_STOCK_ONLY``
* ``WATCH_STOCK_ONLY``
* ``WAIT_FOR_ENTRY_STOCK_ONLY``
* ``READY_TO_RESEARCH_WITH_OPTION``
* ``STOCK_OK_OPTION_BAD``
* ``OPTION_DATA_NOT_AVAILABLE``
* ``NO_TRADE``
* ``INSUFFICIENT_PRICE_HISTORY``

Mapping rules (in evaluation order):

1. Thesis ``INSUFFICIENT_PRICE_HISTORY`` -> final ``INSUFFICIENT_PRICE_HISTORY``.
2. Thesis ``NO_TRADE``                   -> final ``NO_TRADE``.
3. Thesis ``WATCH``                      -> final ``WATCH_STOCK_ONLY``.
4. Thesis ``WAIT_FOR_ENTRY``             -> final ``WAIT_FOR_ENTRY_STOCK_ONLY``.
5. Thesis ``READY_TO_RESEARCH`` + scope ``OPTION_AVAILABLE`` -> ``READY_TO_RESEARCH_WITH_OPTION``.
6. Thesis ``READY_TO_RESEARCH`` + scope ``OPTION_REJECTED``       -> ``STOCK_OK_OPTION_BAD``.
7. Thesis ``READY_TO_RESEARCH`` + scope ``STOCK_ONLY``            ->
   - if ``option_data_requested`` -> ``OPTION_DATA_NOT_AVAILABLE``
   - else                         -> ``READY_TO_RESEARCH_STOCK_ONLY``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.decision.decision_labels import (
    INSUFFICIENT_PRICE_HISTORY,
    NO_TRADE,
    OPTION_DATA_NOT_AVAILABLE,
    READY_TO_RESEARCH_STOCK_ONLY,
    READY_TO_RESEARCH_WITH_OPTION,
    SCOPE_OPTION_AVAILABLE,
    SCOPE_OPTION_REJECTED,
    STOCK_OK_OPTION_BAD,
    THESIS_INSUFFICIENT_PRICE_HISTORY,
    THESIS_NO_TRADE,
    THESIS_READY_TO_RESEARCH,
    THESIS_WAIT_FOR_ENTRY,
    THESIS_WATCH,
    WAIT_FOR_ENTRY_STOCK_ONLY,
    WATCH_STOCK_ONLY,
)
from app.decision.instrument_scope_classifier import InstrumentScope
from app.decision.stock_thesis_decision import StockThesisDecision


@dataclass(frozen=True)
class ActionLabel:
    final_label: str
    rationale: str

    def to_dict(self) -> dict[str, Any]:
        return {"final_label": self.final_label, "rationale": self.rationale}


def classify_action_label(
    thesis: StockThesisDecision,
    scope: InstrumentScope,
) -> ActionLabel:
    label = thesis.thesis_label

    if label == THESIS_INSUFFICIENT_PRICE_HISTORY:
        return ActionLabel(
            final_label=INSUFFICIENT_PRICE_HISTORY,
            rationale="Insufficient price history — no decision is possible.",
        )

    if label == THESIS_NO_TRADE:
        return ActionLabel(
            final_label=NO_TRADE,
            rationale="Stock thesis blocked by Phase 19 sufficiency or Phase 20 hard filters.",
        )

    if label == THESIS_WATCH:
        return ActionLabel(
            final_label=WATCH_STOCK_ONLY,
            rationale="Stock is allowed but the hard filter raised warnings.",
        )

    if label == THESIS_WAIT_FOR_ENTRY:
        return ActionLabel(
            final_label=WAIT_FOR_ENTRY_STOCK_ONLY,
            rationale="Setup is fine but current price is outside the entry zone.",
        )

    # Stock thesis READY_TO_RESEARCH -- scope decides the option suffix.
    if label == THESIS_READY_TO_RESEARCH:
        if scope.scope == SCOPE_OPTION_AVAILABLE:
            return ActionLabel(
                final_label=READY_TO_RESEARCH_WITH_OPTION,
                rationale="Stock thesis is ready and the supplied option passes hard filters.",
            )
        if scope.scope == SCOPE_OPTION_REJECTED:
            return ActionLabel(
                final_label=STOCK_OK_OPTION_BAD,
                rationale=(
                    "Stock thesis is ready but the supplied option fails one or "
                    "more hard filters."
                ),
            )
        # SCOPE_STOCK_ONLY
        if scope.option_data_requested:
            return ActionLabel(
                final_label=OPTION_DATA_NOT_AVAILABLE,
                rationale=(
                    "Stock thesis is ready and option analysis was requested, "
                    "but no option data was supplied."
                ),
            )
        return ActionLabel(
            final_label=READY_TO_RESEARCH_STOCK_ONLY,
            rationale="Stock thesis is ready; no option data requested.",
        )

    # Defensive fallback -- never reached when the thesis labels stay in
    # sync with this classifier, but keeps the gate honest.
    return ActionLabel(
        final_label=NO_TRADE,
        rationale=f"Unknown thesis label '{label}'; defaulting to NO_TRADE.",
    )


__all__ = ["ActionLabel", "classify_action_label"]
