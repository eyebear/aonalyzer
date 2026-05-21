"""Phase 22, step 22.2 — Entry condition builder.

Builds a deterministic ``entry_condition`` object describing the price /
technical state that should be present before the user opens the trade.
Reads only the persisted Phase 12 setup math (entry zone, support,
resistance, current close). When the setup is undefined or the
opportunity is not ready, returns an explicit ``None``-style state so
the dashboard can render it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.action.action_labels import (
    LIFECYCLE_INSUFFICIENT_DATA,
    LIFECYCLE_READY_FOR_RESEARCH,
    LIFECYCLE_REJECTED,
    LIFECYCLE_WAITING_FOR_ENTRY,
    LIFECYCLE_WATCHING,
)


@dataclass(frozen=True)
class StockSetupSnapshot:
    """Subset of the Phase 12 ``StockSetup`` row the builder needs."""

    direction: str | None = None  # LONG / SHORT / UNDEFINED
    current_close: float | None = None
    entry_zone_low: float | None = None
    entry_zone_high: float | None = None
    nearest_support: float | None = None
    nearest_resistance: float | None = None


@dataclass(frozen=True)
class EntryCondition:
    state: str  # READY / WAIT / NOT_APPLICABLE
    direction: str | None
    entry_zone_low: float | None
    entry_zone_high: float | None
    reference_support: float | None
    reference_resistance: float | None
    description: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "direction": self.direction,
            "entry_zone_low": self.entry_zone_low,
            "entry_zone_high": self.entry_zone_high,
            "reference_support": self.reference_support,
            "reference_resistance": self.reference_resistance,
            "description": self.description,
        }


STATE_READY = "READY"
STATE_WAIT = "WAIT"
STATE_NOT_APPLICABLE = "NOT_APPLICABLE"


def build_entry_condition(
    setup: StockSetupSnapshot,
    *,
    lifecycle_state: str,
) -> EntryCondition:
    direction = (setup.direction or "").strip().upper() or None

    if lifecycle_state in (LIFECYCLE_INSUFFICIENT_DATA, LIFECYCLE_REJECTED):
        return EntryCondition(
            state=STATE_NOT_APPLICABLE,
            direction=direction,
            entry_zone_low=None,
            entry_zone_high=None,
            reference_support=None,
            reference_resistance=None,
            description="No entry condition produced because the candidate is not actionable.",
        )

    zone_low = setup.entry_zone_low
    zone_high = setup.entry_zone_high
    if zone_low is not None and zone_high is not None and zone_low > zone_high:
        zone_low, zone_high = zone_high, zone_low

    if zone_low is None or zone_high is None:
        return EntryCondition(
            state=STATE_NOT_APPLICABLE,
            direction=direction,
            entry_zone_low=zone_low,
            entry_zone_high=zone_high,
            reference_support=setup.nearest_support,
            reference_resistance=setup.nearest_resistance,
            description="Entry zone is undefined for the current setup.",
        )

    if lifecycle_state == LIFECYCLE_WAITING_FOR_ENTRY:
        description = (
            "Wait for price to re-enter the zone "
            f"[{zone_low:.2f}, {zone_high:.2f}] before opening the position."
        )
        return EntryCondition(
            state=STATE_WAIT,
            direction=direction,
            entry_zone_low=zone_low,
            entry_zone_high=zone_high,
            reference_support=setup.nearest_support,
            reference_resistance=setup.nearest_resistance,
            description=description,
        )

    if lifecycle_state == LIFECYCLE_WATCHING:
        description = (
            "Observe price action around the entry zone "
            f"[{zone_low:.2f}, {zone_high:.2f}] while warnings clear."
        )
        return EntryCondition(
            state=STATE_WAIT,
            direction=direction,
            entry_zone_low=zone_low,
            entry_zone_high=zone_high,
            reference_support=setup.nearest_support,
            reference_resistance=setup.nearest_resistance,
            description=description,
        )

    if lifecycle_state == LIFECYCLE_READY_FOR_RESEARCH:
        description = (
            "Price is inside the entry zone "
            f"[{zone_low:.2f}, {zone_high:.2f}]; opening is allowed under "
            "the current setup math."
        )
        return EntryCondition(
            state=STATE_READY,
            direction=direction,
            entry_zone_low=zone_low,
            entry_zone_high=zone_high,
            reference_support=setup.nearest_support,
            reference_resistance=setup.nearest_resistance,
            description=description,
        )

    # AWAITING_OPTION_DATA -- stock thesis is ready; entry condition is the
    # same as READY since the only thing missing is the option contract.
    return EntryCondition(
        state=STATE_READY,
        direction=direction,
        entry_zone_low=zone_low,
        entry_zone_high=zone_high,
        reference_support=setup.nearest_support,
        reference_resistance=setup.nearest_resistance,
        description=(
            "Stock entry is ready inside the zone "
            f"[{zone_low:.2f}, {zone_high:.2f}]; option data is needed to "
            "complete the option-aware variant."
        ),
    )


__all__ = [
    "EntryCondition",
    "STATE_NOT_APPLICABLE",
    "STATE_READY",
    "STATE_WAIT",
    "StockSetupSnapshot",
    "build_entry_condition",
]
