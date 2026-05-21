"""Phase 25, step 25.5 — State reason builder.

Turns a ``TransitionPlan`` + the Phase 22 final action label into a
human-readable ``(label, summary)`` pair the history writer can store.
Deterministic and small; the precise content lives in a single lookup
table so dashboards and tests stay stable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.lifecycle.state_transition_engine import (
    KIND_DATA_LOST,
    KIND_DATA_RESTORED,
    KIND_DOWNGRADE,
    KIND_FIRST_OBSERVATION,
    KIND_LATERAL,
    KIND_NO_CHANGE,
    KIND_OPTION_INPUT_NEEDED,
    KIND_OPTION_INPUT_SATISFIED,
    KIND_REACTIVATION,
    KIND_UPGRADE,
    TransitionPlan,
)


@dataclass(frozen=True)
class TransitionReason:
    label: str
    summary: str

    def to_dict(self) -> dict[str, Any]:
        return {"label": self.label, "summary": self.summary}


_LABELS = {
    KIND_FIRST_OBSERVATION: "FIRST_OBSERVATION",
    KIND_NO_CHANGE: "NO_CHANGE",
    KIND_UPGRADE: "UPGRADE",
    KIND_DOWNGRADE: "DOWNGRADE",
    KIND_REACTIVATION: "REACTIVATION",
    KIND_OPTION_INPUT_NEEDED: "OPTION_INPUT_NEEDED",
    KIND_OPTION_INPUT_SATISFIED: "OPTION_INPUT_SATISFIED",
    KIND_DATA_RESTORED: "DATA_RESTORED",
    KIND_DATA_LOST: "DATA_LOST",
    KIND_LATERAL: "LATERAL",
}


def build_transition_reason(
    plan: TransitionPlan,
    *,
    final_action_label: str | None = None,
) -> TransitionReason:
    suffix = f" (action label: {final_action_label})" if final_action_label else ""

    if plan.kind == KIND_FIRST_OBSERVATION:
        summary = (
            f"First lifecycle observation; recording initial state "
            f"{plan.to_state}{suffix}."
        )
    elif plan.kind == KIND_NO_CHANGE:
        summary = (
            f"Re-evaluated in state {plan.to_state}{suffix}; no transition."
        )
    elif plan.kind == KIND_UPGRADE:
        summary = (
            f"Upgrade from {plan.from_state} to {plan.to_state}{suffix}."
        )
    elif plan.kind == KIND_DOWNGRADE:
        summary = (
            f"Downgrade from {plan.from_state} to {plan.to_state}{suffix}."
        )
    elif plan.kind == KIND_REACTIVATION:
        summary = (
            f"Reactivation: moved from terminal {plan.from_state} into "
            f"active {plan.to_state}{suffix}."
        )
    elif plan.kind == KIND_OPTION_INPUT_NEEDED:
        summary = (
            "System now requires a manually pasted option contract before "
            f"the candidate can advance further{suffix}."
        )
    elif plan.kind == KIND_OPTION_INPUT_SATISFIED:
        summary = (
            f"Manual option input received; moving to {plan.to_state}{suffix}."
        )
    elif plan.kind == KIND_DATA_RESTORED:
        summary = (
            f"Data sufficient again; advancing to {plan.to_state}{suffix}."
        )
    elif plan.kind == KIND_DATA_LOST:
        summary = (
            "Data became insufficient; demoting to INSUFFICIENT_DATA"
            + suffix
            + "."
        )
    elif plan.kind == KIND_LATERAL:
        summary = (
            f"Lateral move from {plan.from_state} to {plan.to_state}{suffix}."
        )
    else:
        summary = (
            f"Unclassified transition from {plan.from_state} to "
            f"{plan.to_state}{suffix}."
        )

    label = _LABELS.get(plan.kind, "UNCLASSIFIED")
    return TransitionReason(label=label, summary=summary)


__all__ = ["TransitionReason", "build_transition_reason"]
