"""Phase 22, step 22.8 — Next-review trigger builder.

Says *when* the user should look at this candidate again. Built from
the profile's refresh cadence + the active lifecycle state + any
imminent earnings event.

This module produces a small ``NextReviewTrigger`` dataclass that
populates the ``next_review_trigger`` field of the Phase 22 action
package -- it's guidance text + a cadence string for the dashboard.

It is **distinct** from ``app.review.next_review_trigger_engine``
(Phase 26), which is the operational trigger system that actually
arms persistent ``review_triggers`` rows and enqueues
``review_queue`` items. The two layers complement each other:

* Phase 22 explains, on each action package, *roughly when* the user
  should look at the candidate again.
* Phase 26 actively monitors the database and surfaces a due-review
  task once a real trigger condition (price entering the zone,
  earnings clearing, manual option pasted, etc.) is met.
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
from app.profiles.profile_models import StrategyProfile


@dataclass(frozen=True)
class NextReviewTrigger:
    cadence: str  # MARKET_DATA_REFRESH / EARNINGS_REFRESH / EVENT_DRIVEN / DAILY / NONE
    earliest_review_after_minutes: int | None
    triggers: list[str]
    description: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "cadence": self.cadence,
            "earliest_review_after_minutes": self.earliest_review_after_minutes,
            "triggers": list(self.triggers),
            "description": self.description,
        }


CADENCE_MARKET_DATA = "MARKET_DATA_REFRESH"
CADENCE_DAILY = "DAILY"
CADENCE_EVENT = "EVENT_DRIVEN"
CADENCE_NONE = "NONE"


def build_next_review_trigger(
    *,
    lifecycle_state: str,
    profile: StrategyProfile | None,
    days_to_earnings: int | None = None,
) -> NextReviewTrigger:
    market_minutes = (
        profile.market_data_refresh_minutes if profile is not None else 30
    )
    triggers: list[str] = []

    if lifecycle_state == LIFECYCLE_REJECTED:
        triggers.append("Re-evaluate only after the next full refresh cycle.")
        return NextReviewTrigger(
            cadence=CADENCE_DAILY,
            earliest_review_after_minutes=24 * 60,
            triggers=triggers,
            description="; ".join(triggers),
        )

    if lifecycle_state == LIFECYCLE_INSUFFICIENT_DATA:
        triggers.append(
            "Re-evaluate after the next market-data refresh restores price history."
        )
        return NextReviewTrigger(
            cadence=CADENCE_MARKET_DATA,
            earliest_review_after_minutes=market_minutes,
            triggers=triggers,
            description="; ".join(triggers),
        )

    if lifecycle_state == LIFECYCLE_AWAITING_OPTION_DATA:
        triggers.append(
            "Re-evaluate as soon as a manual option contract is pasted."
        )
        return NextReviewTrigger(
            cadence=CADENCE_EVENT,
            earliest_review_after_minutes=None,
            triggers=triggers,
            description="; ".join(triggers),
        )

    if lifecycle_state in (LIFECYCLE_WATCHING, LIFECYCLE_WAITING_FOR_ENTRY):
        triggers.append(
            f"Re-evaluate after the next market-data refresh (~{market_minutes} minutes)."
        )

    if lifecycle_state == LIFECYCLE_READY_FOR_RESEARCH:
        triggers.append(
            "Re-evaluate after the next market-data refresh or once the user "
            "opens the position."
        )

    if days_to_earnings is not None:
        triggers.append(
            f"Force a review when days_to_earnings drops below the profile's "
            f"risk window ({days_to_earnings} days remaining now)."
        )

    if not triggers:
        triggers.append("No explicit review trigger defined; default to daily review.")

    cadence = (
        CADENCE_MARKET_DATA
        if lifecycle_state
        in (
            LIFECYCLE_READY_FOR_RESEARCH,
            LIFECYCLE_WATCHING,
            LIFECYCLE_WAITING_FOR_ENTRY,
        )
        else CADENCE_DAILY
    )
    return NextReviewTrigger(
        cadence=cadence,
        earliest_review_after_minutes=market_minutes,
        triggers=triggers,
        description="; ".join(triggers),
    )


__all__ = [
    "CADENCE_DAILY",
    "CADENCE_EVENT",
    "CADENCE_MARKET_DATA",
    "CADENCE_NONE",
    "NextReviewTrigger",
    "build_next_review_trigger",
]
