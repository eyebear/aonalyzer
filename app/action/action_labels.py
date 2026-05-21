"""Phase 22 — lifecycle state labels for the action package.

The Phase 21 ``final_action_label`` is the user-facing verdict; the
Phase 22 ``lifecycle_state`` is the opportunity-tracking state. The
mapping is deliberately deterministic and one-way so the dashboard and
the (later) opportunity lifecycle tracker can read either layer
independently.
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

# --- Lifecycle states ------------------------------------------------------

LIFECYCLE_READY_FOR_RESEARCH = "READY_FOR_RESEARCH"
LIFECYCLE_WATCHING = "WATCHING"
LIFECYCLE_WAITING_FOR_ENTRY = "WAITING_FOR_ENTRY"
LIFECYCLE_AWAITING_OPTION_DATA = "AWAITING_OPTION_DATA"
LIFECYCLE_REJECTED = "REJECTED"
LIFECYCLE_INSUFFICIENT_DATA = "INSUFFICIENT_DATA"

_FINAL_TO_LIFECYCLE: dict[str, str] = {
    READY_TO_RESEARCH_STOCK_ONLY: LIFECYCLE_READY_FOR_RESEARCH,
    READY_TO_RESEARCH_WITH_OPTION: LIFECYCLE_READY_FOR_RESEARCH,
    STOCK_OK_OPTION_BAD: LIFECYCLE_READY_FOR_RESEARCH,
    WATCH_STOCK_ONLY: LIFECYCLE_WATCHING,
    WAIT_FOR_ENTRY_STOCK_ONLY: LIFECYCLE_WAITING_FOR_ENTRY,
    OPTION_DATA_NOT_AVAILABLE: LIFECYCLE_AWAITING_OPTION_DATA,
    NO_TRADE: LIFECYCLE_REJECTED,
    INSUFFICIENT_PRICE_HISTORY: LIFECYCLE_INSUFFICIENT_DATA,
}


def lifecycle_state_for(final_label: str) -> str:
    """Return the Phase 22 lifecycle state for a Phase 21 final action label.

    Unknown labels fall back to ``LIFECYCLE_REJECTED`` so an unexpected
    upstream label is never silently treated as a research opportunity.
    """
    return _FINAL_TO_LIFECYCLE.get(final_label, LIFECYCLE_REJECTED)


__all__ = [
    "LIFECYCLE_AWAITING_OPTION_DATA",
    "LIFECYCLE_INSUFFICIENT_DATA",
    "LIFECYCLE_READY_FOR_RESEARCH",
    "LIFECYCLE_REJECTED",
    "LIFECYCLE_WAITING_FOR_ENTRY",
    "LIFECYCLE_WATCHING",
    "lifecycle_state_for",
]
