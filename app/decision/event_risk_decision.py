"""Phase 21, step 21.4 — Event-risk decision.

Combines the news, earnings, and IV signals into a single LOW / MEDIUM /
HIGH / UNKNOWN bucket plus a list of contributing factors. The buckets
are intentionally coarse: the precise per-component math already lives
in the upstream services (earnings risk, IV risk, news importance).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.decision.decision_labels import (
    RISK_HIGH,
    RISK_LOW,
    RISK_MEDIUM,
    RISK_UNKNOWN,
)


@dataclass(frozen=True)
class EventRiskInputs:
    earnings_risk_label: str | None = (
        None  # NO_EARNINGS_NEAR / EARNINGS_INSIDE_WINDOW / EARNINGS_BEFORE_EXPIRATION / ...
    )
    earnings_within_window: bool = False
    earnings_before_expiration: str | None = None  # TRUE / FALSE / NOT_APPLICABLE
    iv_state: str | None = None  # LOW / NORMAL / ELEVATED / HIGH / UNKNOWN
    high_importance_news_count: int = 0
    news_data_available: bool = True


@dataclass(frozen=True)
class EventRiskDecision:
    risk_level: str
    factors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"risk_level": self.risk_level, "factors": list(self.factors)}


def decide_event_risk(inputs: EventRiskInputs) -> EventRiskDecision:
    factors: list[str] = []
    high_count = 0
    medium_count = 0
    unknown_count = 0

    # Earnings -- HIGH if EBE=TRUE or inside-window; LOW if NO_EARNINGS_NEAR.
    ebe = (inputs.earnings_before_expiration or "").upper()
    if ebe == "TRUE":
        high_count += 1
        factors.append("Earnings event falls before the option expiration.")
    elif inputs.earnings_within_window:
        high_count += 1
        factors.append("Earnings event is inside the configured risk window.")
    elif inputs.earnings_risk_label == "NO_EARNINGS_NEAR":
        pass  # contributes LOW
    elif inputs.earnings_risk_label in (None, "", "EARNINGS_DATA_NOT_AVAILABLE"):
        unknown_count += 1
        factors.append("Earnings risk data is not available.")

    # IV state
    iv_state = (inputs.iv_state or "").upper()
    if iv_state == "HIGH":
        high_count += 1
        factors.append("IV is at/above the reject threshold.")
    elif iv_state == "ELEVATED":
        medium_count += 1
        factors.append("IV is elevated (above warning but below reject).")
    elif iv_state in ("", "UNKNOWN"):
        unknown_count += 1
        factors.append("IV state is unknown.")

    # News
    if not inputs.news_data_available:
        unknown_count += 1
        factors.append("No news data available for risk evaluation.")
    elif inputs.high_importance_news_count >= 2:
        medium_count += 1
        factors.append(
            f"{inputs.high_importance_news_count} high-importance news items "
            "in the recent window."
        )
    elif inputs.high_importance_news_count >= 1:
        # Single high-importance headline is informative but not yet medium
        # risk on its own; record it as a factor without bumping the bucket.
        factors.append("1 high-importance news item in the recent window.")

    if high_count > 0:
        return EventRiskDecision(risk_level=RISK_HIGH, factors=factors)
    if medium_count > 0:
        return EventRiskDecision(risk_level=RISK_MEDIUM, factors=factors)
    if unknown_count > 0 and not factors_present_low(factors, inputs):
        return EventRiskDecision(risk_level=RISK_UNKNOWN, factors=factors)
    return EventRiskDecision(
        risk_level=RISK_LOW,
        factors=factors or ["No high-impact event signals."],
    )


def factors_present_low(factors: list[str], inputs: EventRiskInputs) -> bool:
    """If the only data we have is positively "clean", treat as LOW even if
    other components are unknown. Concretely: a confirmed NO_EARNINGS_NEAR
    and a LOW/NORMAL IV state are enough to call the bucket LOW."""
    clean_earnings = inputs.earnings_risk_label == "NO_EARNINGS_NEAR"
    clean_iv = (inputs.iv_state or "").upper() in ("LOW", "NORMAL")
    return clean_earnings and clean_iv


__all__ = [
    "EventRiskDecision",
    "EventRiskInputs",
    "decide_event_risk",
    "factors_present_low",
]
