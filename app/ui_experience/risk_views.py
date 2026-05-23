"""Phase 35 — Earnings / IV Risk display helpers (pure, testable).

Enforces the Phase 35 honesty rules:

* earnings-before-expiration is shown only when an option expiration exists;
* IV rank / percentile / pasted IV are shown only when available;
* missing IV is reported as UNAVAILABLE, never as low risk;
* IV crush risk is described only when the required IV + event data exists.
"""

from __future__ import annotations

from typing import Any

IV_STATE_AVAILABLE = "IV_AVAILABLE"
IV_STATE_UNAVAILABLE = "IV_DATA_NOT_AVAILABLE"


def build_earnings_iv_view(
    *,
    earnings: dict[str, Any] | None,
    iv: dict[str, Any] | None,
    option_expiration_present: bool = False,
    pasted_option_iv: float | None = None,
) -> dict[str, Any]:
    """Assemble the earnings/IV risk view for one symbol."""
    earnings = earnings or {}
    iv = iv or {}

    # --- earnings ---
    next_earnings = earnings.get("next_earnings_datetime_utc")
    days_to_earnings = earnings.get("days_to_earnings")
    earnings_available = bool(next_earnings or days_to_earnings is not None)

    # earnings-before-expiration only meaningful when an expiration exists.
    if option_expiration_present:
        earnings_before_expiration = earnings.get("earnings_before_expiration")
    else:
        earnings_before_expiration = "NOT_APPLICABLE_NO_OPTION_EXPIRATION"

    # --- IV ---
    current_iv = iv.get("current_iv")
    iv_rank = iv.get("iv_rank")
    iv_percentile = iv.get("iv_percentile")
    iv_available = (
        current_iv is not None
        or iv_rank is not None
        or iv_percentile is not None
        or pasted_option_iv is not None
    )
    iv_state = IV_STATE_AVAILABLE if iv_available else IV_STATE_UNAVAILABLE

    # IV crush risk: only described when we have BOTH an IV reading AND a near
    # earnings event. Never fabricated when IV is missing.
    iv_crush = _iv_crush_assessment(
        iv_available=iv_available,
        current_iv=current_iv,
        pasted_option_iv=pasted_option_iv,
        iv_rank=iv_rank,
        days_to_earnings=days_to_earnings,
        earnings_within_window=bool(earnings.get("earnings_within_window")),
    )

    return {
        "earnings": {
            "available": earnings_available,
            "next_earnings_datetime_utc": next_earnings,
            "days_to_earnings": days_to_earnings,
            "earnings_within_window": earnings.get("earnings_within_window"),
            "earnings_before_expiration": earnings_before_expiration,
            "risk_label": earnings.get("risk_label"),
        },
        "iv": {
            "state": iv_state,
            "available": iv_available,
            "current_iv": current_iv,
            "iv_rank": iv_rank,
            "iv_percentile": iv_percentile,
            "pasted_option_iv": pasted_option_iv,
            "detail": None
            if iv_available
            else "IV data is not available — shown as unavailable, not low risk.",
        },
        "iv_crush_risk": iv_crush,
    }


def _iv_crush_assessment(
    *,
    iv_available: bool,
    current_iv: float | None,
    pasted_option_iv: float | None,
    iv_rank: float | None,
    days_to_earnings: int | None,
    earnings_within_window: bool,
) -> dict[str, Any]:
    if not iv_available or days_to_earnings is None:
        return {
            "calculable": False,
            "detail": (
                "IV crush risk not calculable — requires both an IV reading and "
                "a known earnings date."
            ),
        }
    near_earnings = earnings_within_window or (
        days_to_earnings is not None and days_to_earnings <= 7
    )
    elevated = (iv_rank is not None and iv_rank >= 50) or (
        (current_iv or pasted_option_iv or 0) >= 0.5
    )
    if near_earnings and elevated:
        level = "HIGH"
    elif near_earnings:
        level = "MEDIUM"
    else:
        level = "LOW"
    return {
        "calculable": True,
        "level": level,
        "near_earnings": near_earnings,
        "detail": (
            "Long options may lose value to IV crush after the earnings event "
            "if implied volatility is elevated."
            if near_earnings
            else "No imminent earnings event — IV crush risk is low for now."
        ),
    }


__all__ = [
    "IV_STATE_AVAILABLE",
    "IV_STATE_UNAVAILABLE",
    "build_earnings_iv_view",
]
