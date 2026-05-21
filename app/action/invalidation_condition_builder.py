"""Phase 22, step 22.4 — Invalidation condition builder.

Captures the price / event conditions that should make the user abandon
the idea. Reads only persisted setup math + active hard-filter warnings;
does not invent stop levels.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.action.entry_condition_builder import StockSetupSnapshot
from app.hard_filter.hard_filter_gate import (
    EARNINGS_BEFORE_OPTION_EXPIRATION,
    EARNINGS_INSIDE_WINDOW,
    PRICE_TOO_EXTENDED,
    REGIME_OPPOSES_SETUP,
)


@dataclass(frozen=True)
class InvalidationCondition:
    price_invalidation: float | None
    direction: str | None
    triggers: list[str]
    description: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "price_invalidation": self.price_invalidation,
            "direction": self.direction,
            "triggers": list(self.triggers),
            "description": self.description,
        }


def build_invalidation_condition(
    setup: StockSetupSnapshot,
    *,
    stop_price: float | None,
    nearest_support: float | None,
    nearest_resistance: float | None,
    warning_labels: list[str] | None = None,
) -> InvalidationCondition:
    direction = (setup.direction or "").strip().upper() or None
    warnings = list(warning_labels or [])

    invalidation_price = stop_price
    if invalidation_price is None:
        # Fall back to the structural break level when the persisted stop
        # is absent (e.g. setup math is partial).
        if direction == "LONG":
            invalidation_price = nearest_support
        elif direction == "SHORT":
            invalidation_price = nearest_resistance

    triggers: list[str] = []
    if invalidation_price is not None:
        if direction == "LONG":
            triggers.append(
                f"Daily close below {invalidation_price:.2f} invalidates the long thesis."
            )
        elif direction == "SHORT":
            triggers.append(
                f"Daily close above {invalidation_price:.2f} invalidates the short thesis."
            )
        else:
            triggers.append(
                f"Price moving through {invalidation_price:.2f} invalidates the thesis."
            )
    if EARNINGS_BEFORE_OPTION_EXPIRATION in warnings:
        triggers.append(
            "Earnings is scheduled before the option expiration; treat as already invalidated."
        )
    if EARNINGS_INSIDE_WINDOW in warnings:
        triggers.append(
            "Confirmed earnings inside the configured risk window invalidates the option side."
        )
    if PRICE_TOO_EXTENDED in warnings:
        triggers.append(
            "A second close further extending the move invalidates the chase-prevention rule."
        )
    if REGIME_OPPOSES_SETUP in warnings:
        triggers.append(
            "Sustained adverse market regime over several sessions invalidates the setup."
        )

    if not triggers:
        triggers.append(
            "No explicit invalidation level is defined yet; review when setup "
            "math is refreshed."
        )

    description = "; ".join(triggers)
    return InvalidationCondition(
        price_invalidation=invalidation_price,
        direction=direction,
        triggers=triggers,
        description=description,
    )


__all__ = ["InvalidationCondition", "build_invalidation_condition"]
