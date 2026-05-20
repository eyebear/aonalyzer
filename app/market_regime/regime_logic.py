"""Pure, deterministic broad-market regime logic (Phase 13, steps 13.1-13.6).

No I/O and no randomness: every function maps inputs to outputs deterministically
so scoring is fully testable. Missing/short inputs return explicit ``UNKNOWN`` /
``INSUFFICIENT`` states rather than guessed values.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.quant.technical_indicators import simple_moving_average

# Trend labels.
TREND_UP = "UP"
TREND_DOWN = "DOWN"
TREND_SIDEWAYS = "SIDEWAYS"
TREND_INSUFFICIENT = "INSUFFICIENT"

# VIX volatility states.
VIX_CALM = "CALM"
VIX_NORMAL = "NORMAL"
VIX_STRESSED = "STRESSED"
VIX_UNKNOWN = "UNKNOWN"

# 10Y-yield states.
YIELD_RISING = "RISING"
YIELD_FALLING = "FALLING"
YIELD_STABLE = "STABLE"
YIELD_UNKNOWN = "UNKNOWN"

# Composite regime labels.
REGIME_RISK_ON = "RISK_ON"
REGIME_NEUTRAL = "NEUTRAL"
REGIME_RISK_OFF = "RISK_OFF"
REGIME_UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class TrendResult:
    trend: str
    last_close: float | None
    sma_fast: float | None
    sma_slow: float | None
    row_count: int
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "trend": self.trend,
            "last_close": self.last_close,
            "sma_fast": self.sma_fast,
            "sma_slow": self.sma_slow,
            "row_count": self.row_count,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class YieldResult:
    state: str
    level: float | None
    change_pct: float | None
    pressure: bool
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "level": self.level,
            "change_pct": self.change_pct,
            "pressure": self.pressure,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class RegimeResult:
    regime_label: str
    regime_score: int
    uptrend_count: int
    downtrend_count: int
    components: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "regime_label": self.regime_label,
            "regime_score": self.regime_score,
            "uptrend_count": self.uptrend_count,
            "downtrend_count": self.downtrend_count,
            "components": dict(self.components),
        }


def classify_trend(
    closes: list[float],
    fast_period: int = 20,
    slow_period: int = 50,
    min_rows: int = 50,
) -> TrendResult:
    """Classify an index trend from a chronological list of closes.

    UP when the last close is above the slow SMA and the fast SMA is above the
    slow SMA; DOWN for the mirror condition; otherwise SIDEWAYS. Returns
    ``INSUFFICIENT`` when there are too few rows to compute the slow SMA.
    """
    required = max(slow_period, min_rows)
    row_count = len(closes)

    if row_count < required:
        return TrendResult(
            trend=TREND_INSUFFICIENT,
            last_close=closes[-1] if closes else None,
            sma_fast=None,
            sma_slow=None,
            row_count=row_count,
            reason=(
                f"Need at least {required} closes to classify trend; "
                f"found {row_count}."
            ),
        )

    last_close = closes[-1]
    sma_fast = simple_moving_average(closes, fast_period)
    sma_slow = simple_moving_average(closes, slow_period)

    if sma_fast is None or sma_slow is None or last_close is None:
        return TrendResult(
            trend=TREND_INSUFFICIENT,
            last_close=last_close,
            sma_fast=sma_fast,
            sma_slow=sma_slow,
            row_count=row_count,
            reason="Could not compute fast/slow moving averages.",
        )

    if last_close > sma_slow and sma_fast > sma_slow:
        trend = TREND_UP
    elif last_close < sma_slow and sma_fast < sma_slow:
        trend = TREND_DOWN
    else:
        trend = TREND_SIDEWAYS

    return TrendResult(
        trend=trend,
        last_close=last_close,
        sma_fast=sma_fast,
        sma_slow=sma_slow,
        row_count=row_count,
    )


def classify_vix(
    vix_level: float | None,
    calm_threshold: float = 15.0,
    stress_threshold: float = 25.0,
) -> str:
    """Map a VIX level to CALM / NORMAL / STRESSED (UNKNOWN when missing)."""
    if vix_level is None:
        return VIX_UNKNOWN
    if vix_level <= calm_threshold:
        return VIX_CALM
    if vix_level >= stress_threshold:
        return VIX_STRESSED
    return VIX_NORMAL


def classify_yield_pressure(
    closes: list[float],
    lookback_days: int = 20,
    pressure_level: float = 4.5,
    rise_pct: float = 0.10,
) -> YieldResult:
    """Classify 10Y-yield direction and growth-stock pressure.

    Pressure triggers when the yield is RISING by at least ``rise_pct`` over the
    lookback (scale-invariant) OR the current level is at/above ``pressure_level``.
    Returns UNKNOWN with ``pressure=False`` when history is insufficient -- this
    is a non-blocking warning input, never a hard signal.
    """
    if len(closes) < lookback_days + 1:
        return YieldResult(
            state=YIELD_UNKNOWN,
            level=closes[-1] if closes else None,
            change_pct=None,
            pressure=False,
            reason=(
                f"Need at least {lookback_days + 1} yield closes; "
                f"found {len(closes)}."
            ),
        )

    current = closes[-1]
    past = closes[-(lookback_days + 1)]

    change_pct: float | None
    if past:
        change_pct = (current - past) / abs(past)
    else:
        change_pct = None

    if change_pct is None:
        state = YIELD_UNKNOWN
    elif change_pct >= rise_pct:
        state = YIELD_RISING
    elif change_pct <= -rise_pct:
        state = YIELD_FALLING
    else:
        state = YIELD_STABLE

    pressure = state == YIELD_RISING or current >= pressure_level

    return YieldResult(
        state=state,
        level=current,
        change_pct=change_pct,
        pressure=pressure,
    )


def _trend_score(trend: str) -> int:
    if trend == TREND_UP:
        return 1
    if trend == TREND_DOWN:
        return -1
    return 0


def composite_regime(
    spy_trend: str,
    qqq_trend: str,
    iwm_trend: str,
    vix_state: str,
    yield_pressure: bool,
) -> RegimeResult:
    """Combine index trends, VIX state, and yield pressure into a regime label.

    Deterministic additive scoring: each index UP/DOWN contributes +1/-1; VIX
    CALM/STRESSED contributes +1/-1; yield pressure contributes -1. RISK_ON when
    score >= 2, RISK_OFF when score <= -2, else NEUTRAL.
    """
    index_trends = [spy_trend, qqq_trend, iwm_trend]
    uptrend_count = sum(1 for t in index_trends if t == TREND_UP)
    downtrend_count = sum(1 for t in index_trends if t == TREND_DOWN)

    spy_component = _trend_score(spy_trend)
    qqq_component = _trend_score(qqq_trend)
    iwm_component = _trend_score(iwm_trend)

    if vix_state == VIX_CALM:
        vix_component = 1
    elif vix_state == VIX_STRESSED:
        vix_component = -1
    else:
        vix_component = 0

    yield_component = -1 if yield_pressure else 0

    score = (
        spy_component
        + qqq_component
        + iwm_component
        + vix_component
        + yield_component
    )

    if score >= 2:
        label = REGIME_RISK_ON
    elif score <= -2:
        label = REGIME_RISK_OFF
    else:
        label = REGIME_NEUTRAL

    return RegimeResult(
        regime_label=label,
        regime_score=score,
        uptrend_count=uptrend_count,
        downtrend_count=downtrend_count,
        components={
            "spy": spy_component,
            "qqq": qqq_component,
            "iwm": iwm_component,
            "vix": vix_component,
            "yield": yield_component,
        },
    )


__all__ = [
    "REGIME_NEUTRAL",
    "REGIME_RISK_OFF",
    "REGIME_RISK_ON",
    "REGIME_UNKNOWN",
    "TREND_DOWN",
    "TREND_INSUFFICIENT",
    "TREND_SIDEWAYS",
    "TREND_UP",
    "VIX_CALM",
    "VIX_NORMAL",
    "VIX_STRESSED",
    "VIX_UNKNOWN",
    "YIELD_FALLING",
    "YIELD_RISING",
    "YIELD_STABLE",
    "YIELD_UNKNOWN",
    "RegimeResult",
    "TrendResult",
    "YieldResult",
    "classify_trend",
    "classify_vix",
    "classify_yield_pressure",
    "composite_regime",
]
