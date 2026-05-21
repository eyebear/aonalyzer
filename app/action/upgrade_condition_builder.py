"""Phase 22, step 22.5 — Upgrade condition builder.

Describes what would move the candidate to a *better* state (e.g.
WATCH -> READY_FOR_RESEARCH, WAIT_FOR_ENTRY -> READY_FOR_RESEARCH,
AWAITING_OPTION_DATA -> READY_FOR_RESEARCH_WITH_OPTION). Pure
deterministic mapping from the current lifecycle state + the present
warnings; never invents future events.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.action.action_labels import (
    LIFECYCLE_AWAITING_OPTION_DATA,
    LIFECYCLE_INSUFFICIENT_DATA,
    LIFECYCLE_READY_FOR_RESEARCH,
    LIFECYCLE_REJECTED,
    LIFECYCLE_WAITING_FOR_ENTRY,
    LIFECYCLE_WATCHING,
)
from app.hard_filter.hard_filter_gate import (
    EARNINGS_BEFORE_OPTION_EXPIRATION,
    EARNINGS_INSIDE_WINDOW,
    REGIME_OPPOSES_SETUP,
)


@dataclass(frozen=True)
class UpgradeCondition:
    triggers: list[str]
    description: str

    def to_dict(self) -> dict[str, Any]:
        return {"triggers": list(self.triggers), "description": self.description}


def build_upgrade_condition(
    *,
    lifecycle_state: str,
    warning_labels: list[str] | None = None,
    entry_zone_low: float | None = None,
    entry_zone_high: float | None = None,
) -> UpgradeCondition:
    warnings = list(warning_labels or [])
    triggers: list[str] = []

    if lifecycle_state == LIFECYCLE_REJECTED:
        triggers.append(
            "Candidate is rejected; an upgrade requires the underlying "
            "hard-filter rules to pass on the next refresh."
        )

    if lifecycle_state == LIFECYCLE_INSUFFICIENT_DATA:
        triggers.append(
            "Refresh market data and confirm sufficient price history before "
            "re-evaluating."
        )

    if lifecycle_state == LIFECYCLE_WAITING_FOR_ENTRY:
        if entry_zone_low is not None and entry_zone_high is not None:
            triggers.append(
                "Price re-entering the zone "
                f"[{entry_zone_low:.2f}, {entry_zone_high:.2f}] upgrades to READY_FOR_RESEARCH."
            )
        else:
            triggers.append("Price returning into a defined entry zone upgrades to READY_FOR_RESEARCH.")

    if lifecycle_state == LIFECYCLE_WATCHING:
        if REGIME_OPPOSES_SETUP in warnings:
            triggers.append("Market regime turning supportive upgrades to READY_FOR_RESEARCH.")
        if EARNINGS_INSIDE_WINDOW in warnings:
            triggers.append(
                "Earnings event passing without disruption upgrades to READY_FOR_RESEARCH."
            )
        if not triggers:
            triggers.append(
                "All open hard-filter warnings clearing upgrades to READY_FOR_RESEARCH."
            )

    if lifecycle_state == LIFECYCLE_AWAITING_OPTION_DATA:
        triggers.append(
            "Pasting a manual option contract that passes hard filters upgrades to "
            "READY_FOR_RESEARCH with the option side enabled."
        )

    if lifecycle_state == LIFECYCLE_READY_FOR_RESEARCH:
        triggers.append(
            "Already at the highest lifecycle state; an upgrade is the user's "
            "decision to actually open the position."
        )

    if EARNINGS_BEFORE_OPTION_EXPIRATION in warnings:
        triggers.append(
            "Selecting an option expiration after the earnings date removes the "
            "non-bypassable EARNINGS_BEFORE_OPTION_EXPIRATION block."
        )

    if not triggers:
        triggers.append("No upgrade trigger is defined for the current state.")

    return UpgradeCondition(triggers=triggers, description="; ".join(triggers))


__all__ = ["UpgradeCondition", "build_upgrade_condition"]
