"""Phase 25, step 25.4 — State transition engine.

Pure logic that decides:

* what the target lifecycle state should be given the Phase 22 lifecycle
  state on the latest action package; and
* whether a transition from the current persisted state to the target
  state is allowed (it always is, in the Phase 25 design -- the engine
  is non-restrictive so the lifecycle accurately mirrors reality -- but
  the engine classifies the *kind* of transition so the reason builder
  can phrase it correctly).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.lifecycle.lifecycle_states import (
    ACTIVE_STATES,
    STATE_INSUFFICIENT_DATA,
    STATE_READY_FOR_RESEARCH,
    STATE_REJECTED,
    STATE_WAIT_FOR_MANUAL_OPTION_INPUT,
    STATE_WAITING_FOR_ENTRY,
    STATE_WATCHING,
    normalize_phase22_state,
)


# --- Transition kinds (used by the reason builder) -------------------------

KIND_NO_CHANGE = "NO_CHANGE"
KIND_FIRST_OBSERVATION = "FIRST_OBSERVATION"
KIND_UPGRADE = "UPGRADE"
KIND_DOWNGRADE = "DOWNGRADE"
KIND_REACTIVATION = "REACTIVATION"
KIND_OPTION_INPUT_NEEDED = "OPTION_INPUT_NEEDED"
KIND_OPTION_INPUT_SATISFIED = "OPTION_INPUT_SATISFIED"
KIND_DATA_RESTORED = "DATA_RESTORED"
KIND_DATA_LOST = "DATA_LOST"
KIND_LATERAL = "LATERAL"


@dataclass(frozen=True)
class TransitionPlan:
    from_state: str | None
    to_state: str
    kind: str
    is_change: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "from_state": self.from_state,
            "to_state": self.to_state,
            "kind": self.kind,
            "is_change": self.is_change,
        }


# Rough "rank" used to classify a transition as an upgrade vs downgrade.
# Higher = closer to actionable.
_STATE_RANK = {
    STATE_REJECTED: 0,
    STATE_INSUFFICIENT_DATA: 0,
    STATE_WAITING_FOR_ENTRY: 1,
    STATE_WATCHING: 1,
    STATE_WAIT_FOR_MANUAL_OPTION_INPUT: 2,
    STATE_READY_FOR_RESEARCH: 3,
}


def plan_transition(
    *,
    current_state: str | None,
    target_state_phase22: str,
) -> TransitionPlan:
    target_state = normalize_phase22_state(target_state_phase22)

    if current_state is None:
        return TransitionPlan(
            from_state=None,
            to_state=target_state,
            kind=KIND_FIRST_OBSERVATION,
            is_change=True,
        )

    if current_state == target_state:
        return TransitionPlan(
            from_state=current_state,
            to_state=target_state,
            kind=KIND_NO_CHANGE,
            is_change=False,
        )

    # Reactivation: rejected -> active. ``INSUFFICIENT_DATA -> active`` is
    # classified as ``DATA_RESTORED`` below instead (a separate, narrower
    # event so the trace distinguishes "data came back" from "thesis healed").
    if current_state == STATE_REJECTED and target_state in ACTIVE_STATES:
        return TransitionPlan(
            from_state=current_state,
            to_state=target_state,
            kind=KIND_REACTIVATION,
            is_change=True,
        )

    # Option-input handshake: entering / leaving WAIT_FOR_MANUAL_OPTION_INPUT
    # is a distinct semantic event.
    if target_state == STATE_WAIT_FOR_MANUAL_OPTION_INPUT:
        return TransitionPlan(
            from_state=current_state,
            to_state=target_state,
            kind=KIND_OPTION_INPUT_NEEDED,
            is_change=True,
        )
    if current_state == STATE_WAIT_FOR_MANUAL_OPTION_INPUT:
        return TransitionPlan(
            from_state=current_state,
            to_state=target_state,
            kind=KIND_OPTION_INPUT_SATISFIED,
            is_change=True,
        )

    # Data-availability transitions.
    if (
        current_state == STATE_INSUFFICIENT_DATA
        and target_state != STATE_INSUFFICIENT_DATA
    ):
        return TransitionPlan(
            from_state=current_state,
            to_state=target_state,
            kind=KIND_DATA_RESTORED,
            is_change=True,
        )
    if (
        current_state != STATE_INSUFFICIENT_DATA
        and target_state == STATE_INSUFFICIENT_DATA
    ):
        return TransitionPlan(
            from_state=current_state,
            to_state=target_state,
            kind=KIND_DATA_LOST,
            is_change=True,
        )

    # Up / down moves based on the rough rank.
    current_rank = _STATE_RANK.get(current_state, 0)
    target_rank = _STATE_RANK.get(target_state, 0)
    if target_rank > current_rank:
        return TransitionPlan(
            from_state=current_state,
            to_state=target_state,
            kind=KIND_UPGRADE,
            is_change=True,
        )
    if target_rank < current_rank:
        return TransitionPlan(
            from_state=current_state,
            to_state=target_state,
            kind=KIND_DOWNGRADE,
            is_change=True,
        )
    return TransitionPlan(
        from_state=current_state,
        to_state=target_state,
        kind=KIND_LATERAL,
        is_change=True,
    )


__all__ = [
    "KIND_DATA_LOST",
    "KIND_DATA_RESTORED",
    "KIND_DOWNGRADE",
    "KIND_FIRST_OBSERVATION",
    "KIND_LATERAL",
    "KIND_NO_CHANGE",
    "KIND_OPTION_INPUT_NEEDED",
    "KIND_OPTION_INPUT_SATISFIED",
    "KIND_REACTIVATION",
    "KIND_UPGRADE",
    "TransitionPlan",
    "plan_transition",
]
