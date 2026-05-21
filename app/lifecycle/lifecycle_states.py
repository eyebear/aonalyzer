"""Phase 25 — Opportunity lifecycle state constants.

The lifecycle layer is one step removed from the Phase 22 ``lifecycle_state``
field on the action package: Phase 22 emits a per-decision lifecycle
state for the *current* evaluation; Phase 25 tracks the *persistent*
state of each opportunity over time, including reactivations and user
review.

Phase 25 introduces ``WAIT_FOR_MANUAL_OPTION_INPUT`` as the canonical
"system is waiting for the user to paste an option contract" state.
Phase 22 already emits ``AWAITING_OPTION_DATA`` for the same upstream
condition; the Phase 25 state manager **normalizes** the Phase 22
value into the Phase 25 canonical value when materialising the
lifecycle row -- the Phase 22 contract stays unchanged.
"""

from __future__ import annotations

from app.action.action_labels import (
    LIFECYCLE_AWAITING_OPTION_DATA,
    LIFECYCLE_INSUFFICIENT_DATA,
    LIFECYCLE_READY_FOR_RESEARCH,
    LIFECYCLE_REJECTED,
    LIFECYCLE_WAITING_FOR_ENTRY,
    LIFECYCLE_WATCHING,
)

# --- Phase 25 lifecycle states ---------------------------------------------

STATE_READY_FOR_RESEARCH = "READY_FOR_RESEARCH"
STATE_WATCHING = "WATCHING"
STATE_WAITING_FOR_ENTRY = "WAITING_FOR_ENTRY"
STATE_WAIT_FOR_MANUAL_OPTION_INPUT = "WAIT_FOR_MANUAL_OPTION_INPUT"
STATE_REJECTED = "REJECTED"
STATE_INSUFFICIENT_DATA = "INSUFFICIENT_DATA"

ALL_STATES = frozenset(
    {
        STATE_READY_FOR_RESEARCH,
        STATE_WATCHING,
        STATE_WAITING_FOR_ENTRY,
        STATE_WAIT_FOR_MANUAL_OPTION_INPUT,
        STATE_REJECTED,
        STATE_INSUFFICIENT_DATA,
    }
)

ACTIVE_STATES = frozenset(
    {
        STATE_READY_FOR_RESEARCH,
        STATE_WATCHING,
        STATE_WAITING_FOR_ENTRY,
        STATE_WAIT_FOR_MANUAL_OPTION_INPUT,
    }
)

TERMINAL_STATES = frozenset(
    {STATE_REJECTED, STATE_INSUFFICIENT_DATA}
)

# --- Phase 22 -> Phase 25 normalization map --------------------------------
#
# ``AWAITING_OPTION_DATA`` is the legacy Phase 22 spelling for what
# Phase 25 records as ``WAIT_FOR_MANUAL_OPTION_INPUT``. Phase 22 keeps
# emitting the legacy value (unchanged) so existing Phase 22 tests stay
# green; Phase 25 normalizes on the way in.

PHASE22_TO_PHASE25: dict[str, str] = {
    LIFECYCLE_READY_FOR_RESEARCH: STATE_READY_FOR_RESEARCH,
    LIFECYCLE_WATCHING: STATE_WATCHING,
    LIFECYCLE_WAITING_FOR_ENTRY: STATE_WAITING_FOR_ENTRY,
    LIFECYCLE_AWAITING_OPTION_DATA: STATE_WAIT_FOR_MANUAL_OPTION_INPUT,
    LIFECYCLE_REJECTED: STATE_REJECTED,
    LIFECYCLE_INSUFFICIENT_DATA: STATE_INSUFFICIENT_DATA,
}


def normalize_phase22_state(state: str) -> str:
    """Return the Phase 25 canonical state for a Phase 22 lifecycle string.

    Unknown values fall through unchanged so the caller can decide how to
    treat them (Phase 25 service treats them as the literal Phase 22
    string).
    """
    return PHASE22_TO_PHASE25.get(state, state)


# --- User review status ----------------------------------------------------

REVIEW_UNREVIEWED = "UNREVIEWED"
REVIEW_REVIEWED = "REVIEWED"
REVIEW_DISMISSED = "DISMISSED"

ALL_REVIEW_STATUSES = frozenset(
    {REVIEW_UNREVIEWED, REVIEW_REVIEWED, REVIEW_DISMISSED}
)


# --- Transition trigger sources -------------------------------------------

TRIGGER_SYSTEM_EVALUATION = "SYSTEM_EVALUATION"
TRIGGER_SYSTEM_REACTIVATION = "SYSTEM_REACTIVATION"
TRIGGER_USER = "USER"
TRIGGER_AGENT_JOB = "AGENT_JOB"

# --- Source phases ---------------------------------------------------------

SOURCE_PHASE_PHASE22 = "PHASE22_ACTION_PACKAGE"
SOURCE_PHASE_USER = "USER_INPUT"
SOURCE_PHASE_REACTIVATION = "REACTIVATION_ENGINE"
SOURCE_PHASE_UPDATE_JOB = "LIFECYCLE_UPDATE_JOB"


__all__ = [
    "ACTIVE_STATES",
    "ALL_REVIEW_STATUSES",
    "ALL_STATES",
    "PHASE22_TO_PHASE25",
    "REVIEW_DISMISSED",
    "REVIEW_REVIEWED",
    "REVIEW_UNREVIEWED",
    "SOURCE_PHASE_PHASE22",
    "SOURCE_PHASE_REACTIVATION",
    "SOURCE_PHASE_UPDATE_JOB",
    "SOURCE_PHASE_USER",
    "STATE_INSUFFICIENT_DATA",
    "STATE_READY_FOR_RESEARCH",
    "STATE_REJECTED",
    "STATE_WAITING_FOR_ENTRY",
    "STATE_WAIT_FOR_MANUAL_OPTION_INPUT",
    "STATE_WATCHING",
    "TERMINAL_STATES",
    "TRIGGER_AGENT_JOB",
    "TRIGGER_SYSTEM_EVALUATION",
    "TRIGGER_SYSTEM_REACTIVATION",
    "TRIGGER_USER",
    "normalize_phase22_state",
]
