"""Hard filters and the volume preference for manually pasted option contracts.

Phase 15, steps 15.1-15.6. Every filter is pure and deterministic, and only
runs when the field it needs was actually parsed -- a missing field yields a
``SKIPPED`` outcome, never a failure. This keeps option analysis non-blocking:
absent option data is a clean "not enough info", not a rejection.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Filter outcome statuses.
PASS = "PASS"
FAIL = "FAIL"
SKIPPED = "SKIPPED"
WARN = "WARN"

# Rejection / warning labels owned by these filters.
DTE_TOO_SHORT = "DTE_TOO_SHORT"
OPTION_TOO_EXPENSIVE = "OPTION_TOO_EXPENSIVE"
SPREAD_TOO_WIDE = "SPREAD_TOO_WIDE"
LOW_OPEN_INTEREST = "LOW_OPEN_INTEREST"
LOW_VOLUME = "LOW_VOLUME"


@dataclass(frozen=True)
class FilterOutcome:
    name: str
    status: str
    label: str | None = None
    detail: str | None = None
    value: float | None = None

    @property
    def is_hard_fail(self) -> bool:
        return self.status == FAIL

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "label": self.label,
            "detail": self.detail,
            "value": self.value,
        }


def compute_mid(bid: float | None, ask: float | None) -> float | None:
    """Mid price when both sides of a positive market are present."""
    if bid is None or ask is None:
        return None
    if bid <= 0 or ask <= 0 or ask < bid:
        return None
    return (bid + ask) / 2.0


def compute_premium(
    bid: float | None,
    ask: float | None,
    last_price: float | None,
) -> float | None:
    """Per-share premium: prefer mid, fall back to last price."""
    mid = compute_mid(bid, ask)
    if mid is not None:
        return mid
    if last_price is not None and last_price > 0:
        return last_price
    return None


def filter_dte(
    dte: int | None,
    dte_min: int,
    dte_max: int,
) -> FilterOutcome:
    if dte is None:
        return FilterOutcome("dte", SKIPPED, detail="No expiration / DTE parsed.")
    if dte < dte_min:
        return FilterOutcome(
            "dte",
            FAIL,
            label=DTE_TOO_SHORT,
            detail=f"DTE {dte} is below the minimum {dte_min}.",
            value=float(dte),
        )
    return FilterOutcome("dte", PASS, detail=f"DTE {dte} within range.", value=float(dte))


def filter_premium_budget(
    premium: float | None,
    premium_min_usd: float,
    premium_max_usd: float,
) -> FilterOutcome:
    if premium is None:
        return FilterOutcome(
            "premium_budget", SKIPPED, detail="No mid/last premium available."
        )
    contract_cost = premium * 100.0
    if contract_cost > premium_max_usd:
        return FilterOutcome(
            "premium_budget",
            FAIL,
            label=OPTION_TOO_EXPENSIVE,
            detail=(
                f"Contract cost ${contract_cost:.2f} exceeds the budget "
                f"maximum ${premium_max_usd:.2f}."
            ),
            value=contract_cost,
        )
    return FilterOutcome(
        "premium_budget",
        PASS,
        detail=f"Contract cost ${contract_cost:.2f} within budget.",
        value=contract_cost,
    )


def filter_spread(
    bid: float | None,
    ask: float | None,
    max_spread_percent: float,
) -> FilterOutcome:
    mid = compute_mid(bid, ask)
    if mid is None:
        return FilterOutcome(
            "spread", SKIPPED, detail="No usable bid/ask to measure spread."
        )
    spread_percent = (ask - bid) / mid * 100.0  # type: ignore[operator]
    if spread_percent > max_spread_percent:
        return FilterOutcome(
            "spread",
            FAIL,
            label=SPREAD_TOO_WIDE,
            detail=(
                f"Bid/ask spread {spread_percent:.2f}% exceeds the maximum "
                f"{max_spread_percent:.2f}%."
            ),
            value=spread_percent,
        )
    return FilterOutcome(
        "spread",
        PASS,
        detail=f"Spread {spread_percent:.2f}% within tolerance.",
        value=spread_percent,
    )


def filter_open_interest(
    open_interest: int | None,
    min_open_interest: int,
) -> FilterOutcome:
    if open_interest is None:
        return FilterOutcome(
            "open_interest", SKIPPED, detail="No open interest parsed."
        )
    if open_interest < min_open_interest:
        return FilterOutcome(
            "open_interest",
            FAIL,
            label=LOW_OPEN_INTEREST,
            detail=(
                f"Open interest {open_interest} is below the minimum "
                f"{min_open_interest}."
            ),
            value=float(open_interest),
        )
    return FilterOutcome(
        "open_interest",
        PASS,
        detail=f"Open interest {open_interest} adequate.",
        value=float(open_interest),
    )


def volume_preference(
    volume: int | None,
    min_volume_preference: int,
) -> FilterOutcome:
    """Soft preference (WARN, never a hard fail) for actively traded contracts."""
    if volume is None:
        return FilterOutcome("volume", SKIPPED, detail="No volume parsed.")
    if volume < min_volume_preference:
        return FilterOutcome(
            "volume",
            WARN,
            label=LOW_VOLUME,
            detail=(
                f"Volume {volume} is below the preferred minimum "
                f"{min_volume_preference}."
            ),
            value=float(volume),
        )
    return FilterOutcome(
        "volume",
        PASS,
        detail=f"Volume {volume} indicates active trading.",
        value=float(volume),
    )


__all__ = [
    "DTE_TOO_SHORT",
    "FAIL",
    "LOW_OPEN_INTEREST",
    "LOW_VOLUME",
    "OPTION_TOO_EXPENSIVE",
    "PASS",
    "SKIPPED",
    "SPREAD_TOO_WIDE",
    "WARN",
    "FilterOutcome",
    "compute_mid",
    "compute_premium",
    "filter_dte",
    "filter_open_interest",
    "filter_premium_budget",
    "filter_spread",
    "volume_preference",
]
