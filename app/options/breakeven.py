"""Breakeven calculation, only when strike + premium + type exist (Phase 15, step 15.9).

CALL breakeven = strike + premium; PUT breakeven = strike - premium. Returns
None whenever a required input is missing -- nothing is invented.
"""

from __future__ import annotations

OPTION_TYPE_CALL = "CALL"
OPTION_TYPE_PUT = "PUT"


def normalize_option_type(option_type: str | None) -> str | None:
    if option_type is None:
        return None
    value = option_type.strip().upper()
    if value in {"CALL", "C"}:
        return OPTION_TYPE_CALL
    if value in {"PUT", "P"}:
        return OPTION_TYPE_PUT
    return None


def is_call(option_type: str | None) -> bool:
    return normalize_option_type(option_type) == OPTION_TYPE_CALL


def is_put(option_type: str | None) -> bool:
    return normalize_option_type(option_type) == OPTION_TYPE_PUT


def compute_breakeven(
    option_type: str | None,
    strike: float | None,
    premium: float | None,
) -> float | None:
    """Per-share breakeven price, or None if any input is missing/unusable."""
    normalized = normalize_option_type(option_type)
    if normalized is None or strike is None or premium is None:
        return None
    if premium < 0 or strike <= 0:
        return None
    if normalized == OPTION_TYPE_CALL:
        return strike + premium
    return strike - premium


def breakeven_distance_percent(
    option_type: str | None,
    breakeven: float | None,
    underlying_price: float | None,
) -> float | None:
    """How far the breakeven sits from the current underlying, in the
    unfavorable direction for the option type (positive = further to travel)."""
    normalized = normalize_option_type(option_type)
    if normalized is None or breakeven is None or underlying_price is None:
        return None
    if underlying_price <= 0:
        return None
    if normalized == OPTION_TYPE_CALL:
        return (breakeven - underlying_price) / underlying_price * 100.0
    return (underlying_price - breakeven) / underlying_price * 100.0


__all__ = [
    "OPTION_TYPE_CALL",
    "OPTION_TYPE_PUT",
    "breakeven_distance_percent",
    "compute_breakeven",
    "is_call",
    "is_put",
    "normalize_option_type",
]
