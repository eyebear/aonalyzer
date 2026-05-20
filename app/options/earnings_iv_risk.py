"""Earnings / IV-crush option risk, only when data exists (Phase 15, step 15.11).

Flags the IV-crush risk of holding an option through an earnings event: if
earnings fall on/before the option expiration and IV is elevated, an IV crush
after the report can hurt the position. This is a soft, non-blocking warning --
it never rejects a contract on its own and is skipped when dates/IV are missing.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

EARNINGS_IV_RISK = "EARNINGS_IV_RISK"


@dataclass(frozen=True)
class EarningsIvRiskResult:
    has_risk: bool
    status: str  # "RISK" | "OK" | "SKIPPED"
    label: str | None
    earnings_before_expiration: bool | None
    days_to_earnings: int | None
    detail: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "has_risk": self.has_risk,
            "status": self.status,
            "label": self.label,
            "earnings_before_expiration": self.earnings_before_expiration,
            "days_to_earnings": self.days_to_earnings,
            "detail": self.detail,
        }


def assess_earnings_iv_risk(
    earnings_date: date | None,
    expiration_date: date | None,
    iv_percent: float | None,
    *,
    iv_warning_threshold: float,
    reference_date: date | None = None,
) -> EarningsIvRiskResult:
    if earnings_date is None or expiration_date is None:
        return EarningsIvRiskResult(
            has_risk=False,
            status="SKIPPED",
            label=None,
            earnings_before_expiration=None,
            days_to_earnings=None,
            detail="Need both an earnings date and an expiration date.",
        )

    earnings_before_expiration = earnings_date <= expiration_date
    days_to_earnings = None
    if reference_date is not None:
        days_to_earnings = (earnings_date - reference_date).days

    iv_elevated = iv_percent is not None and iv_percent >= iv_warning_threshold

    if earnings_before_expiration and iv_elevated:
        return EarningsIvRiskResult(
            has_risk=True,
            status="RISK",
            label=EARNINGS_IV_RISK,
            earnings_before_expiration=True,
            days_to_earnings=days_to_earnings,
            detail=(
                "Earnings fall before option expiration with elevated IV; "
                "IV crush after the report is a risk."
            ),
        )

    return EarningsIvRiskResult(
        has_risk=False,
        status="OK",
        label=None,
        earnings_before_expiration=earnings_before_expiration,
        days_to_earnings=days_to_earnings,
        detail=(
            "Earnings after expiration or IV not elevated."
            if not earnings_before_expiration
            else "Earnings before expiration but IV is not elevated."
        ),
    )


__all__ = [
    "EARNINGS_IV_RISK",
    "EarningsIvRiskResult",
    "assess_earnings_iv_risk",
]
