"""Pure, deterministic stock setup detection (Phase 14, steps 14.1-14.8).

Classifies a single primary setup type from technical indicators (Phase 11),
support/resistance + risk/reward math (Phase 12), and market regime / sector
strength context (Phase 13), and assigns a 0-100 quality score. Stock-only:
option data is never consulted. No randomness, no I/O -- every input maps to a
deterministic output, so classifications and scores are fully testable.

Setup types (core stock-only output):
    PULLBACK_LONG, BREAKOUT_RETEST_LONG, SECTOR_STRENGTH_LONG,
    BREAKDOWN_SHORT, OVERSOLD_BOUNCE_WATCH, NO_TRADE
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.market_regime.regime_logic import REGIME_RISK_OFF, REGIME_RISK_ON
from app.market_regime.sector_strength import SECTOR_OUTPERFORM, SECTOR_UNDERPERFORM

# Setup types.
SETUP_PULLBACK_LONG = "PULLBACK_LONG"
SETUP_BREAKOUT_RETEST_LONG = "BREAKOUT_RETEST_LONG"
SETUP_SECTOR_STRENGTH_LONG = "SECTOR_STRENGTH_LONG"
SETUP_BREAKDOWN_SHORT = "BREAKDOWN_SHORT"
SETUP_OVERSOLD_BOUNCE_WATCH = "OVERSOLD_BOUNCE_WATCH"
SETUP_NO_TRADE = "NO_TRADE"

LONG_SETUP_TYPES = frozenset(
    {SETUP_PULLBACK_LONG, SETUP_BREAKOUT_RETEST_LONG, SETUP_SECTOR_STRENGTH_LONG}
)

# Trade directions.
DIRECTION_LONG = "LONG"
DIRECTION_SHORT = "SHORT"
DIRECTION_WATCH = "WATCH"
DIRECTION_NONE = "NONE"

# Data sufficiency.
SUFFICIENT = "SUFFICIENT"
INSUFFICIENT_INPUT = "INSUFFICIENT_INPUT"

# Base quality scores per setup type.
_BASE_SCORE = {
    SETUP_PULLBACK_LONG: 50,
    SETUP_BREAKOUT_RETEST_LONG: 50,
    SETUP_SECTOR_STRENGTH_LONG: 45,
    SETUP_BREAKDOWN_SHORT: 45,
    SETUP_OVERSOLD_BOUNCE_WATCH: 30,
    SETUP_NO_TRADE: 0,
}


@dataclass(frozen=True)
class SetupInputs:
    close: float | None = None
    sma_20: float | None = None
    sma_50: float | None = None
    sma_200: float | None = None
    rsi_14: float | None = None
    macd_histogram: float | None = None
    atr_14: float | None = None
    volume_ratio: float | None = None
    bollinger_lower: float | None = None
    bollinger_upper: float | None = None

    nearest_support: float | None = None
    nearest_resistance: float | None = None
    swing_high: float | None = None
    swing_low: float | None = None
    risk_reward: float | None = None

    regime_label: str | None = None
    sector_trend: str | None = None
    sector_rs_rank: int | None = None


@dataclass(frozen=True)
class SetupParams:
    rsi_oversold: float = 30.0
    rsi_pullback_ceiling: float = 55.0
    pullback_atr_mult: float = 0.5
    breakout_retest_tolerance: float = 0.03
    breakdown_tolerance: float = 0.01
    min_risk_reward: float = 2.0
    sector_strong_max_rank: int = 2
    volume_confirm_ratio: float = 1.2


@dataclass(frozen=True)
class SetupDetectionResult:
    setup_type: str
    direction: str
    score: int
    data_sufficiency_status: str
    reasons: list[str] = field(default_factory=list)
    components: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "setup_type": self.setup_type,
            "direction": self.direction,
            "score": self.score,
            "data_sufficiency_status": self.data_sufficiency_status,
            "reasons": list(self.reasons),
            "components": dict(self.components),
        }


def _has_core(inp: SetupInputs) -> bool:
    return inp.close is not None and inp.sma_20 is not None and inp.sma_50 is not None


def _is_uptrend(inp: SetupInputs) -> bool:
    return _has_core(inp) and inp.close > inp.sma_50 and inp.sma_20 > inp.sma_50


def _is_downtrend(inp: SetupInputs) -> bool:
    return _has_core(inp) and inp.close < inp.sma_50 and inp.sma_20 < inp.sma_50


def _is_oversold(inp: SetupInputs, params: SetupParams) -> bool:
    return inp.rsi_14 is not None and inp.rsi_14 <= params.rsi_oversold


def _is_pullback_long(inp: SetupInputs, params: SetupParams) -> bool:
    if not _is_uptrend(inp):
        return False
    if inp.rsi_14 is None or not (params.rsi_oversold < inp.rsi_14 <= params.rsi_pullback_ceiling):
        return False
    # Price has pulled back toward the 20-day MA while holding above the 50-day MA.
    if inp.atr_14 is not None:
        ceiling = inp.sma_20 + params.pullback_atr_mult * inp.atr_14
    else:
        ceiling = inp.sma_20 * 1.01
    return inp.close <= ceiling and inp.close >= inp.sma_50


def _is_breakout_retest_long(inp: SetupInputs, params: SetupParams) -> bool:
    if not _is_uptrend(inp):
        return False
    if inp.nearest_resistance is None or inp.nearest_resistance <= 0:
        return False
    tol = params.breakout_retest_tolerance
    lower = inp.nearest_resistance * (1 - tol)
    upper = inp.nearest_resistance * (1 + tol)
    return lower <= inp.close <= upper


def _is_sector_strength_long(inp: SetupInputs, params: SetupParams) -> bool:
    if not _is_uptrend(inp):
        return False
    if inp.regime_label != REGIME_RISK_ON:
        return False
    if inp.sector_trend != SECTOR_OUTPERFORM:
        return False
    return inp.sector_rs_rank is None or inp.sector_rs_rank <= params.sector_strong_max_rank


def _is_breakdown_short(inp: SetupInputs, params: SetupParams) -> bool:
    if not _is_downtrend(inp):
        return False
    if inp.nearest_support is None or inp.nearest_support <= 0:
        return False
    at_or_below_support = inp.close <= inp.nearest_support * (1 + params.breakdown_tolerance)
    momentum_ok = inp.macd_histogram is None or inp.macd_histogram < 0
    return at_or_below_support and momentum_ok


def _score(
    setup_type: str,
    direction: str,
    inp: SetupInputs,
    params: SetupParams,
) -> tuple[int, dict[str, int]]:
    components: dict[str, int] = {"base": _BASE_SCORE[setup_type]}

    if setup_type in LONG_SETUP_TYPES or setup_type == SETUP_BREAKDOWN_SHORT:
        if inp.risk_reward is not None and inp.risk_reward >= params.min_risk_reward:
            components["risk_reward"] = 10

        if inp.sma_50 is not None and inp.sma_200 is not None:
            if direction == DIRECTION_LONG and inp.sma_50 > inp.sma_200:
                components["trend_alignment"] = 10
            elif direction == DIRECTION_SHORT and inp.sma_50 < inp.sma_200:
                components["trend_alignment"] = 10

        if inp.volume_ratio is not None and inp.volume_ratio >= params.volume_confirm_ratio:
            components["volume_confirm"] = 5

        if direction == DIRECTION_LONG:
            if inp.regime_label == REGIME_RISK_ON:
                components["regime"] = 10
            elif inp.regime_label == REGIME_RISK_OFF:
                components["regime"] = -10
            if inp.sector_trend == SECTOR_OUTPERFORM:
                components["sector"] = 5
            elif inp.sector_trend == SECTOR_UNDERPERFORM:
                components["sector"] = -5
        elif direction == DIRECTION_SHORT:
            if inp.regime_label == REGIME_RISK_OFF:
                components["regime"] = 10
            elif inp.regime_label == REGIME_RISK_ON:
                components["regime"] = -10

    elif setup_type == SETUP_OVERSOLD_BOUNCE_WATCH:
        if inp.rsi_14 is not None and inp.rsi_14 <= params.rsi_oversold - 10:
            components["deep_oversold"] = 10
        if (
            inp.bollinger_lower is not None
            and inp.close is not None
            and inp.close <= inp.bollinger_lower
        ):
            components["below_lower_band"] = 5

    score = sum(components.values())
    score = max(0, min(100, score))
    return score, components


def detect_setup(
    inputs: SetupInputs,
    params: SetupParams | None = None,
) -> SetupDetectionResult:
    """Classify a single primary setup type and score it deterministically."""
    params = params or SetupParams()
    reasons: list[str] = []

    if not _has_core(inputs):
        return SetupDetectionResult(
            setup_type=SETUP_NO_TRADE,
            direction=DIRECTION_NONE,
            score=0,
            data_sufficiency_status=INSUFFICIENT_INPUT,
            reasons=["Missing core technical inputs (close / SMA20 / SMA50)."],
            components={"base": 0},
        )

    setup_type: str | None = None
    direction = DIRECTION_NONE

    if _is_uptrend(inputs):
        if _is_pullback_long(inputs, params):
            setup_type, direction = SETUP_PULLBACK_LONG, DIRECTION_LONG
            reasons.append(
                "Uptrend with pullback toward the 20-day MA holding above the 50-day MA."
            )
        elif _is_breakout_retest_long(inputs, params):
            setup_type, direction = SETUP_BREAKOUT_RETEST_LONG, DIRECTION_LONG
            reasons.append("Uptrend retesting the prior breakout / resistance level.")
        elif _is_sector_strength_long(inputs, params):
            setup_type, direction = SETUP_SECTOR_STRENGTH_LONG, DIRECTION_LONG
            reasons.append("Uptrend supported by RISK_ON regime and an outperforming sector.")
    elif _is_downtrend(inputs):
        if not _is_oversold(inputs, params) and _is_breakdown_short(inputs, params):
            setup_type, direction = SETUP_BREAKDOWN_SHORT, DIRECTION_SHORT
            reasons.append("Downtrend breaking below support with negative momentum.")

    if setup_type is None:
        if _is_oversold(inputs, params):
            setup_type, direction = SETUP_OVERSOLD_BOUNCE_WATCH, DIRECTION_WATCH
            reasons.append(
                "Oversold (RSI <= threshold): watch-only for a potential rebound, no entry."
            )
        else:
            setup_type, direction = SETUP_NO_TRADE, DIRECTION_NONE
            reasons.append("No clear setup pattern matched; rejecting as NO_TRADE.")

    score, components = _score(setup_type, direction, inputs, params)

    return SetupDetectionResult(
        setup_type=setup_type,
        direction=direction,
        score=score,
        data_sufficiency_status=SUFFICIENT,
        reasons=reasons,
        components=components,
    )


__all__ = [
    "DIRECTION_LONG",
    "DIRECTION_NONE",
    "DIRECTION_SHORT",
    "DIRECTION_WATCH",
    "INSUFFICIENT_INPUT",
    "LONG_SETUP_TYPES",
    "SETUP_BREAKDOWN_SHORT",
    "SETUP_BREAKOUT_RETEST_LONG",
    "SETUP_NO_TRADE",
    "SETUP_OVERSOLD_BOUNCE_WATCH",
    "SETUP_PULLBACK_LONG",
    "SETUP_SECTOR_STRENGTH_LONG",
    "SUFFICIENT",
    "SetupDetectionResult",
    "SetupInputs",
    "SetupParams",
    "detect_setup",
]
