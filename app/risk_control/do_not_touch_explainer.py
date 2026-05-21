"""Phase 24, step 24.7 — Do-Not-Touch explainer.

Turns a ``FreezeRecommendation`` or a persisted ``DoNotTouchItem`` into
a human-readable explanation block (a structured ``DoNotTouchExplanation``
dataclass with ``to_dict()``). The explainer is the single place that
phrases the "why is this frozen" surface used by routes and the
dashboard.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.risk_control.do_not_touch_categories import (
    FREEZE_CATEGORY_EARNINGS_BEFORE_EXPIRATION,
    FREEZE_CATEGORY_EXTREME_OPTION_LIQUIDITY_RISK,
    FREEZE_CATEGORY_EXTREME_OPTION_VOLATILITY,
    FREEZE_CATEGORY_MANUAL,
    FREEZE_CATEGORY_REPEATED_REJECTIONS,
)


@dataclass(frozen=True)
class DoNotTouchExplanation:
    category: str
    severity: str
    headline: str
    body: str
    user_actions: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "severity": self.severity,
            "headline": self.headline,
            "body": self.body,
            "user_actions": list(self.user_actions),
        }


_HEADLINES = {
    FREEZE_CATEGORY_EARNINGS_BEFORE_EXPIRATION:
        "Frozen: earnings event falls before option expiration",
    FREEZE_CATEGORY_EXTREME_OPTION_VOLATILITY:
        "Frozen: pasted option contract has extreme implied volatility",
    FREEZE_CATEGORY_EXTREME_OPTION_LIQUIDITY_RISK:
        "Frozen: pasted option contract has unacceptable liquidity",
    FREEZE_CATEGORY_REPEATED_REJECTIONS:
        "Frozen: repeated hard rejections in the recent window",
    FREEZE_CATEGORY_MANUAL:
        "Frozen: manual user freeze",
}

_BODIES = {
    FREEZE_CATEGORY_EARNINGS_BEFORE_EXPIRATION: (
        "The Phase 20 hard-filter gate reports EARNINGS_BEFORE_OPTION_EXPIRATION. "
        "The candidate is frozen until the earnings risk clears."
    ),
    FREEZE_CATEGORY_EXTREME_OPTION_VOLATILITY: (
        "The pasted option contract failed the IV reject threshold. The "
        "candidate is frozen so the system does not surface action items "
        "based on a contract that is mispriced on a vol basis."
    ),
    FREEZE_CATEGORY_EXTREME_OPTION_LIQUIDITY_RISK: (
        "The pasted option contract failed both the maximum spread and the "
        "minimum open-interest filters. The contract is functionally "
        "untradeable; the freeze prevents accidental action."
    ),
    FREEZE_CATEGORY_REPEATED_REJECTIONS: (
        "The symbol has produced multiple hard stock rejections inside the "
        "configured window. The freeze enforces a cool-down before the next "
        "review."
    ),
    FREEZE_CATEGORY_MANUAL: (
        "The freeze was applied manually by the user. It remains active until "
        "explicitly released."
    ),
}

_USER_ACTIONS = {
    FREEZE_CATEGORY_EARNINGS_BEFORE_EXPIRATION: [
        "Pick an option expiration *after* the earnings date.",
        "Wait for the earnings event to pass; the freeze auto-releases after.",
    ],
    FREEZE_CATEGORY_EXTREME_OPTION_VOLATILITY: [
        "Wait for IV to fall back below the profile reject threshold.",
        "Paste a contract with a longer expiration where vol is calmer.",
    ],
    FREEZE_CATEGORY_EXTREME_OPTION_LIQUIDITY_RISK: [
        "Paste a more liquid contract (tighter spread, higher OI).",
        "Wait for the cool-down window; the freeze auto-releases.",
    ],
    FREEZE_CATEGORY_REPEATED_REJECTIONS: [
        "Wait for the cool-down window to pass.",
        "Review the underlying setup; conditions may have meaningfully changed.",
    ],
    FREEZE_CATEGORY_MANUAL: [
        "Release the freeze via the API or dashboard when ready.",
    ],
}


def explain_freeze(
    *,
    category: str,
    severity: str,
    reason_summary: str | None = None,
) -> DoNotTouchExplanation:
    headline = _HEADLINES.get(category, f"Frozen: {category}")
    body = _BODIES.get(
        category,
        reason_summary or f"Freeze category {category}.",
    )
    if reason_summary and category in _BODIES:
        body = f"{body} ({reason_summary})"
    return DoNotTouchExplanation(
        category=category,
        severity=severity,
        headline=headline,
        body=body,
        user_actions=list(_USER_ACTIONS.get(category, [])),
    )


__all__ = ["DoNotTouchExplanation", "explain_freeze"]
