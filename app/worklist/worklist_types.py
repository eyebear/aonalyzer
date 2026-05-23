"""Phase 27 — Today's Research Worklist type / source / status constants.

Single source of truth for worklist item types, the source layer each item
was generated from, item statuses, and the deterministic priority/type
ordering used by the ranker. Keeping these here means the generator, ranker,
service, routes, and tests never drift.

The new Phase 27 worklist type is ``PASTE_OPTION_DATA``: it asks the user to
paste a manual option contract for a setup whose *stock* thesis is valid but
whose option expression cannot be evaluated because manual option data is
unavailable or incomplete. It is never generated for a stock-blocked
candidate (insufficient price history / no stock setup).
"""

from __future__ import annotations

# --- Worklist item types ----------------------------------------------------

WORKLIST_ACTION_READY = "ACTION_READY"
WORKLIST_ACTION_WATCH = "ACTION_WATCH"
WORKLIST_ACTION_WAIT = "ACTION_WAIT"
WORKLIST_DUE_REVIEW = "DUE_REVIEW"
WORKLIST_RISK_ALERT = "RISK_ALERT"
WORKLIST_IMPORTANT_EVENT = "IMPORTANT_EVENT"
WORKLIST_EXPERIENCE_WARNING = "EXPERIENCE_WARNING"
WORKLIST_PASTE_OPTION_DATA = "PASTE_OPTION_DATA"

ALL_WORKLIST_TYPES = frozenset(
    {
        WORKLIST_ACTION_READY,
        WORKLIST_ACTION_WATCH,
        WORKLIST_ACTION_WAIT,
        WORKLIST_DUE_REVIEW,
        WORKLIST_RISK_ALERT,
        WORKLIST_IMPORTANT_EVENT,
        WORKLIST_EXPERIENCE_WARNING,
        WORKLIST_PASTE_OPTION_DATA,
    }
)

# --- Source layers ----------------------------------------------------------

SOURCE_ACTION_SUGGESTION = "ACTION_SUGGESTION"
SOURCE_REVIEW_QUEUE = "REVIEW_QUEUE"
SOURCE_RISK_ALERT = "RISK_ALERT"
SOURCE_IMPORTANT_EVENT = "IMPORTANT_EVENT"
SOURCE_EXPERIENCE_WARNING = "EXPERIENCE_WARNING"
SOURCE_MANUAL_OPTION_PASTE = "MANUAL_OPTION_PASTE"

ALL_SOURCES = frozenset(
    {
        SOURCE_ACTION_SUGGESTION,
        SOURCE_REVIEW_QUEUE,
        SOURCE_RISK_ALERT,
        SOURCE_IMPORTANT_EVENT,
        SOURCE_EXPERIENCE_WARNING,
        SOURCE_MANUAL_OPTION_PASTE,
    }
)

# --- Item statuses ----------------------------------------------------------

STATUS_OPEN = "OPEN"
STATUS_DONE = "DONE"
STATUS_DISMISSED = "DISMISSED"

ALL_STATUSES = frozenset({STATUS_OPEN, STATUS_DONE, STATUS_DISMISSED})
ACTIVE_STATUSES = frozenset({STATUS_OPEN})

# --- Priority ---------------------------------------------------------------

PRIORITY_HIGH = "HIGH"
PRIORITY_MEDIUM = "MEDIUM"
PRIORITY_LOW = "LOW"

# Numeric rank for deterministic sorting (lower sorts first / higher urgency).
PRIORITY_ORDER: dict[str, int] = {
    PRIORITY_HIGH: 0,
    PRIORITY_MEDIUM: 1,
    PRIORITY_LOW: 2,
}

# Secondary deterministic ordering by worklist type when priority ties.
# Risk first, then due reviews, then ready actions, then the paste prompt,
# then watch/wait, events, and finally experience warnings.
TYPE_ORDER: dict[str, int] = {
    WORKLIST_RISK_ALERT: 0,
    WORKLIST_DUE_REVIEW: 1,
    WORKLIST_ACTION_READY: 2,
    WORKLIST_PASTE_OPTION_DATA: 3,
    WORKLIST_ACTION_WAIT: 4,
    WORKLIST_ACTION_WATCH: 5,
    WORKLIST_IMPORTANT_EVENT: 6,
    WORKLIST_EXPERIENCE_WARNING: 7,
}


def priority_rank(priority: str) -> int:
    return PRIORITY_ORDER.get((priority or "").upper(), 99)


def type_rank(worklist_type: str) -> int:
    return TYPE_ORDER.get((worklist_type or "").upper(), 99)


__all__ = [
    "ACTIVE_STATUSES",
    "ALL_SOURCES",
    "ALL_STATUSES",
    "ALL_WORKLIST_TYPES",
    "PRIORITY_HIGH",
    "PRIORITY_LOW",
    "PRIORITY_MEDIUM",
    "PRIORITY_ORDER",
    "SOURCE_ACTION_SUGGESTION",
    "SOURCE_EXPERIENCE_WARNING",
    "SOURCE_IMPORTANT_EVENT",
    "SOURCE_MANUAL_OPTION_PASTE",
    "SOURCE_REVIEW_QUEUE",
    "SOURCE_RISK_ALERT",
    "STATUS_DISMISSED",
    "STATUS_DONE",
    "STATUS_OPEN",
    "TYPE_ORDER",
    "WORKLIST_ACTION_READY",
    "WORKLIST_ACTION_WAIT",
    "WORKLIST_ACTION_WATCH",
    "WORKLIST_DUE_REVIEW",
    "WORKLIST_EXPERIENCE_WARNING",
    "WORKLIST_IMPORTANT_EVENT",
    "WORKLIST_PASTE_OPTION_DATA",
    "WORKLIST_RISK_ALERT",
    "priority_rank",
    "type_rank",
]
