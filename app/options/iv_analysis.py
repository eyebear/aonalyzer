"""Implied-volatility risk analysis, only when IV was parsed (Phase 15, step 15.8).

IV input may be a fraction (0.65) or a percent (65); it is normalized to percent
before comparison against the profile's warning/reject thresholds. Missing IV is
a clean SKIPPED state with ``UNKNOWN`` -- IV is a non-blocking input.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.options.option_filters import FAIL, PASS, SKIPPED, WARN, FilterOutcome

IV_TOO_HIGH = "IV_TOO_HIGH"

IV_STATE_LOW = "LOW"
IV_STATE_ELEVATED = "ELEVATED"
IV_STATE_HIGH = "HIGH"
IV_STATE_UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class IvResult:
    iv_percent: float | None
    state: str
    outcome: FilterOutcome

    def to_dict(self) -> dict[str, Any]:
        return {
            "iv_percent": self.iv_percent,
            "state": self.state,
            "outcome": self.outcome.to_dict(),
        }


def normalize_iv_to_percent(
    iv_raw: float | None,
    fraction_cutoff: float = 5.0,
) -> float | None:
    """Normalize IV to percentage points. Values <= cutoff are treated as a
    fraction (0.65 -> 65); larger values are assumed already in percent."""
    if iv_raw is None:
        return None
    if iv_raw <= fraction_cutoff:
        return iv_raw * 100.0
    return iv_raw


def analyze_iv(
    iv_raw: float | None,
    *,
    warning_threshold: float,
    reject_threshold: float,
    fraction_cutoff: float = 5.0,
) -> IvResult:
    iv_percent = normalize_iv_to_percent(iv_raw, fraction_cutoff)

    if iv_percent is None:
        return IvResult(
            iv_percent=None,
            state=IV_STATE_UNKNOWN,
            outcome=FilterOutcome("iv", SKIPPED, detail="No implied volatility parsed."),
        )

    if iv_percent >= reject_threshold:
        return IvResult(
            iv_percent=iv_percent,
            state=IV_STATE_HIGH,
            outcome=FilterOutcome(
                "iv",
                FAIL,
                label=IV_TOO_HIGH,
                detail=(
                    f"IV {iv_percent:.1f}% at/above the reject threshold "
                    f"{reject_threshold:.1f}%."
                ),
                value=iv_percent,
            ),
        )

    if iv_percent >= warning_threshold:
        return IvResult(
            iv_percent=iv_percent,
            state=IV_STATE_ELEVATED,
            outcome=FilterOutcome(
                "iv",
                WARN,
                detail=(
                    f"IV {iv_percent:.1f}% is elevated (>= warning threshold "
                    f"{warning_threshold:.1f}%) but below reject."
                ),
                value=iv_percent,
            ),
        )

    return IvResult(
        iv_percent=iv_percent,
        state=IV_STATE_LOW,
        outcome=FilterOutcome(
            "iv", PASS, detail=f"IV {iv_percent:.1f}% within normal range.", value=iv_percent
        ),
    )


__all__ = [
    "IV_STATE_ELEVATED",
    "IV_STATE_HIGH",
    "IV_STATE_LOW",
    "IV_STATE_UNKNOWN",
    "IV_TOO_HIGH",
    "IvResult",
    "analyze_iv",
    "normalize_iv_to_percent",
]
