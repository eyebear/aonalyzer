"""Phase 22, step 22.7 — Watch condition builder.

When the lifecycle state is ``WATCHING`` (or ``WAITING_FOR_ENTRY``),
this builder describes *what to watch* concretely -- price levels,
event categories, or hard-filter labels that should change before the
candidate is upgraded.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.action.action_labels import (
    LIFECYCLE_AWAITING_OPTION_DATA,
    LIFECYCLE_READY_FOR_RESEARCH,
    LIFECYCLE_WAITING_FOR_ENTRY,
    LIFECYCLE_WATCHING,
)


@dataclass(frozen=True)
class WatchCondition:
    active: bool
    observations: list[str]
    description: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "active": self.active,
            "observations": list(self.observations),
            "description": self.description,
        }


def build_watch_condition(
    *,
    lifecycle_state: str,
    entry_zone_low: float | None = None,
    entry_zone_high: float | None = None,
    warning_labels: list[str] | None = None,
    next_earnings_iso: str | None = None,
) -> WatchCondition:
    warnings = list(warning_labels or [])
    observations: list[str] = []

    if lifecycle_state == LIFECYCLE_WAITING_FOR_ENTRY:
        if entry_zone_low is not None and entry_zone_high is not None:
            observations.append(
                "Watch for a daily close re-entering the zone "
                f"[{entry_zone_low:.2f}, {entry_zone_high:.2f}]."
            )
        observations.append(
            "Confirm volume picks up as price approaches the zone."
        )

    if lifecycle_state == LIFECYCLE_WATCHING:
        for w in warnings:
            observations.append(
                f"Watch for the '{w}' warning to clear on the next refresh."
            )
        if not observations:
            observations.append(
                "Watch for any new hard-filter signal before re-classification."
            )

    if lifecycle_state == LIFECYCLE_AWAITING_OPTION_DATA:
        observations.append(
            "Watch the manual option input endpoint for a contract matching the "
            "option_contract_criteria."
        )

    if next_earnings_iso is not None and lifecycle_state in (
        LIFECYCLE_WATCHING,
        LIFECYCLE_WAITING_FOR_ENTRY,
        LIFECYCLE_AWAITING_OPTION_DATA,
        LIFECYCLE_READY_FOR_RESEARCH,
    ):
        observations.append(
            f"Track upcoming earnings date {next_earnings_iso} relative to the "
            "configured risk window."
        )

    active = lifecycle_state in (
        LIFECYCLE_WATCHING,
        LIFECYCLE_WAITING_FOR_ENTRY,
        LIFECYCLE_AWAITING_OPTION_DATA,
    )

    if not observations:
        observations.append("No active observation is required.")

    return WatchCondition(
        active=active,
        observations=observations,
        description="; ".join(observations),
    )


__all__ = ["WatchCondition", "build_watch_condition"]
