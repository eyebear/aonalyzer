"""Phase 38 — user action / override / outcome constants.

Single source of truth for the action types the user can record, the override
types the detector can classify, and the deterministic outcome classifications
the tracker assigns. A user disagreement is stored as an override and only
classified as right/wrong later from real forward outcomes — never assumed.
"""

from __future__ import annotations

# --- User action types ------------------------------------------------------

ACTION_REVIEW = "REVIEW"
ACTION_WATCH = "WATCH"
ACTION_IGNORE = "IGNORE"
ACTION_REJECT = "REJECT"
ACTION_MANUAL_TRADE = "MANUAL_TRADE"
ACTION_PASTE_OPTION = "PASTE_OPTION"

ALL_ACTION_TYPES = frozenset(
    {
        ACTION_REVIEW,
        ACTION_WATCH,
        ACTION_IGNORE,
        ACTION_REJECT,
        ACTION_MANUAL_TRADE,
        ACTION_PASTE_OPTION,
    }
)

# Actions that mean "the user passed on a candidate".
PASS_ACTIONS = frozenset({ACTION_IGNORE, ACTION_REJECT})
# Actions that mean "the user acted on a candidate".
ACT_ACTIONS = frozenset({ACTION_MANUAL_TRADE})

# --- System verdict groupings ----------------------------------------------

SYSTEM_REJECTION_LABELS = frozenset({"NO_TRADE", "INSUFFICIENT_PRICE_HISTORY"})
SYSTEM_READY_LABELS = frozenset(
    {"READY_TO_RESEARCH_STOCK_ONLY", "READY_TO_RESEARCH_WITH_OPTION"}
)

# --- Override types ---------------------------------------------------------

OVERRIDE_TRADED_AGAINST_REJECTION = "TRADED_AGAINST_REJECTION"
OVERRIDE_IGNORED_RECOMMENDATION = "IGNORED_RECOMMENDATION"

ALL_OVERRIDE_TYPES = frozenset(
    {OVERRIDE_TRADED_AGAINST_REJECTION, OVERRIDE_IGNORED_RECOMMENDATION}
)

# --- Outcome classifications ------------------------------------------------

OUTCOME_USER_RIGHT = "USER_RIGHT"
OUTCOME_SYSTEM_RIGHT = "SYSTEM_RIGHT"
OUTCOME_NEUTRAL = "NEUTRAL"
OUTCOME_PENDING = "PENDING"

ALL_OUTCOME_CLASSIFICATIONS = frozenset(
    {OUTCOME_USER_RIGHT, OUTCOME_SYSTEM_RIGHT, OUTCOME_NEUTRAL, OUTCOME_PENDING}
)

# Option-data availability snapshot at action time.
OPTION_DATA_PRESENT = "OPTION_DATA_PRESENT"
OPTION_DATA_ABSENT = "OPTION_DATA_ABSENT"


__all__ = [
    "ACTION_IGNORE",
    "ACTION_MANUAL_TRADE",
    "ACTION_PASTE_OPTION",
    "ACTION_REJECT",
    "ACTION_REVIEW",
    "ACTION_WATCH",
    "ACT_ACTIONS",
    "ALL_ACTION_TYPES",
    "ALL_OUTCOME_CLASSIFICATIONS",
    "ALL_OVERRIDE_TYPES",
    "OPTION_DATA_ABSENT",
    "OPTION_DATA_PRESENT",
    "OUTCOME_NEUTRAL",
    "OUTCOME_PENDING",
    "OUTCOME_SYSTEM_RIGHT",
    "OUTCOME_USER_RIGHT",
    "OVERRIDE_IGNORED_RECOMMENDATION",
    "OVERRIDE_TRADED_AGAINST_REJECTION",
    "PASS_ACTIONS",
    "SYSTEM_READY_LABELS",
    "SYSTEM_REJECTION_LABELS",
]
