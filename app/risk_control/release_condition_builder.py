"""Phase 24, step 24.5 — Release condition builder.

For each freeze category, builds a deterministic ``ReleaseCondition``
that says how the freeze can be lifted (time-based, event-based, or
manual-only) and produces an ``expires_at`` timestamp where appropriate.

The builder never re-derives anything from market data; it consumes
the classifier inputs.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from app.risk_control.do_not_touch_categories import (
    DEFAULT_FREEZE_DAYS_EARNINGS,
    DEFAULT_FREEZE_DAYS_EXTREME_LIQUIDITY,
    DEFAULT_FREEZE_DAYS_EXTREME_VOL,
    DEFAULT_FREEZE_DAYS_MANUAL,
    DEFAULT_FREEZE_DAYS_REPEATED_REJECTIONS,
    FREEZE_CATEGORY_EARNINGS_BEFORE_EXPIRATION,
    FREEZE_CATEGORY_EXTREME_OPTION_LIQUIDITY_RISK,
    FREEZE_CATEGORY_EXTREME_OPTION_VOLATILITY,
    FREEZE_CATEGORY_MANUAL,
    FREEZE_CATEGORY_REPEATED_REJECTIONS,
    RELEASE_KIND_EVENT,
    RELEASE_KIND_MANUAL,
    RELEASE_KIND_TIME,
)


@dataclass(frozen=True)
class ReleaseCondition:
    kind: str
    label: str
    description: str
    expires_at: datetime | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "label": self.label,
            "description": self.description,
            "expires_at": self.expires_at.isoformat()
            if self.expires_at is not None
            else None,
        }


def build_release_condition(
    *,
    category: str,
    now: datetime | None = None,
    earnings_datetime_utc: datetime | None = None,
    override_expires_at: datetime | None = None,
) -> ReleaseCondition:
    now = now or datetime.now(timezone.utc)

    if category == FREEZE_CATEGORY_EARNINGS_BEFORE_EXPIRATION:
        expires_at = override_expires_at
        if expires_at is None and earnings_datetime_utc is not None:
            # Auto-release a day after earnings clears.
            expires_at = earnings_datetime_utc + timedelta(
                days=DEFAULT_FREEZE_DAYS_EARNINGS
            )
        if expires_at is None:
            expires_at = now + timedelta(days=DEFAULT_FREEZE_DAYS_EARNINGS + 7)
        return ReleaseCondition(
            kind=RELEASE_KIND_EVENT,
            label="EARNINGS_EVENT_CLEARS",
            description=(
                "Release once the earnings event has passed and the option "
                "expiration risk is no longer present."
            ),
            expires_at=expires_at,
        )

    if category == FREEZE_CATEGORY_EXTREME_OPTION_VOLATILITY:
        expires_at = override_expires_at or (
            now + timedelta(days=DEFAULT_FREEZE_DAYS_EXTREME_VOL)
        )
        return ReleaseCondition(
            kind=RELEASE_KIND_TIME,
            label="VOLATILITY_COOL_DOWN",
            description=(
                "Release automatically after the volatility cool-down window; "
                "or manually once IV has fallen back below the reject threshold."
            ),
            expires_at=expires_at,
        )

    if category == FREEZE_CATEGORY_EXTREME_OPTION_LIQUIDITY_RISK:
        expires_at = override_expires_at or (
            now + timedelta(days=DEFAULT_FREEZE_DAYS_EXTREME_LIQUIDITY)
        )
        return ReleaseCondition(
            kind=RELEASE_KIND_TIME,
            label="LIQUIDITY_REPLENISHES",
            description=(
                "Release automatically after the liquidity cool-down; or "
                "manually once spread and open interest improve."
            ),
            expires_at=expires_at,
        )

    if category == FREEZE_CATEGORY_REPEATED_REJECTIONS:
        expires_at = override_expires_at or (
            now + timedelta(days=DEFAULT_FREEZE_DAYS_REPEATED_REJECTIONS)
        )
        return ReleaseCondition(
            kind=RELEASE_KIND_TIME,
            label="REJECTION_COOLDOWN",
            description=(
                "Release automatically after the cool-down window; or manually "
                "once the underlying conditions have changed."
            ),
            expires_at=expires_at,
        )

    if category == FREEZE_CATEGORY_MANUAL:
        if DEFAULT_FREEZE_DAYS_MANUAL is None and override_expires_at is None:
            expires_at = None
        else:
            expires_at = override_expires_at or (
                now + timedelta(days=DEFAULT_FREEZE_DAYS_MANUAL or 0)
            )
        return ReleaseCondition(
            kind=RELEASE_KIND_MANUAL,
            label="MANUAL_RELEASE",
            description=(
                "Manual freeze; remains active until released by the user."
            ),
            expires_at=expires_at,
        )

    # Defensive fallback -- treat unknown categories as time-based, short.
    return ReleaseCondition(
        kind=RELEASE_KIND_TIME,
        label="DEFAULT_RELEASE",
        description=f"Default release window for category {category}.",
        expires_at=override_expires_at or (now + timedelta(days=7)),
    )


__all__ = ["ReleaseCondition", "build_release_condition"]
