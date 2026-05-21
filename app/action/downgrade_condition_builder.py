"""Phase 22, step 22.6 — Downgrade condition builder.

Describes what would move the candidate to a *worse* state (e.g.
READY -> WATCH, WATCH -> REJECTED). Symmetric to the upgrade builder.
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
    EARNINGS_INSIDE_WINDOW,
    PRICE_TOO_EXTENDED,
    REGIME_OPPOSES_SETUP,
    WEAK_STOCK_RISK_REWARD,
)


@dataclass(frozen=True)
class DowngradeCondition:
    triggers: list[str]
    description: str

    def to_dict(self) -> dict[str, Any]:
        return {"triggers": list(self.triggers), "description": self.description}


def build_downgrade_condition(
    *,
    lifecycle_state: str,
    warning_labels: list[str] | None = None,
    stop_price: float | None = None,
    direction: str | None = None,
) -> DowngradeCondition:
    warnings = list(warning_labels or [])
    triggers: list[str] = []

    if lifecycle_state == LIFECYCLE_READY_FOR_RESEARCH:
        triggers.append(
            "A new hard-filter warning (regime turn, earnings inside window, "
            "or price extension) downgrades to WATCH."
        )
        triggers.append(
            "Price leaving the entry zone downgrades to WAIT_FOR_ENTRY."
        )

    if lifecycle_state == LIFECYCLE_WATCHING:
        triggers.append(
            "Additional warning labels or a deteriorating R:R downgrade to REJECTED."
        )
        if EARNINGS_INSIDE_WINDOW in warnings:
            triggers.append(
                "Earnings event confirmed inside the option's expiration window "
                "downgrades to REJECTED."
            )

    if lifecycle_state == LIFECYCLE_WAITING_FOR_ENTRY:
        if stop_price is not None and direction == "LONG":
            triggers.append(
                f"Daily close below {stop_price:.2f} downgrades to REJECTED."
            )
        elif stop_price is not None and direction == "SHORT":
            triggers.append(
                f"Daily close above {stop_price:.2f} downgrades to REJECTED."
            )
        else:
            triggers.append("Structural break of the setup downgrades to REJECTED.")

    if lifecycle_state == LIFECYCLE_AWAITING_OPTION_DATA:
        triggers.append(
            "A stock-side warning appearing on the next refresh downgrades to WATCH."
        )

    if lifecycle_state == LIFECYCLE_INSUFFICIENT_DATA:
        triggers.append(
            "Continued absence of price history downgrades to REJECTED on the "
            "next refresh cycle."
        )

    if lifecycle_state == LIFECYCLE_REJECTED:
        triggers.append(
            "Already at the lowest lifecycle state; no further downgrade is possible."
        )

    if WEAK_STOCK_RISK_REWARD in warnings:
        triggers.append(
            "Stock R:R drifting below profile minimum downgrades to REJECTED."
        )
    if PRICE_TOO_EXTENDED in warnings:
        triggers.append(
            "Further extension above support / SMA50 downgrades to REJECTED."
        )
    if REGIME_OPPOSES_SETUP in warnings and lifecycle_state not in (
        LIFECYCLE_REJECTED,
        LIFECYCLE_INSUFFICIENT_DATA,
    ):
        triggers.append(
            "Regime turning sharply against the setup downgrades to WATCH or REJECTED."
        )

    if not triggers:
        triggers.append("No downgrade trigger is defined for the current state.")

    return DowngradeCondition(triggers=triggers, description="; ".join(triggers))


__all__ = ["DowngradeCondition", "build_downgrade_condition"]
