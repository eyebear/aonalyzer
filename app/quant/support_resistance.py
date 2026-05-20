from __future__ import annotations

from dataclasses import dataclass, field

from app.quant.swing_detector import (
    latest_swing_high_above,
    latest_swing_low_below,
)

SETUP_DIRECTION_LONG = "LONG"
SETUP_DIRECTION_UNDEFINED = "UNDEFINED"

STOP_METHOD_ATR = "ATR_1_5X"
STOP_METHOD_SWING_LOW_BUFFER = "SWING_LOW_BUFFER"
STOP_METHOD_UNDEFINED = "UNDEFINED"

ATR_STOP_MULTIPLIER = 1.5
ATR_ENTRY_ZONE_MULTIPLIER = 0.5
SWING_LOW_STOP_BUFFER_PERCENT = 0.02
FALLBACK_ENTRY_ZONE_PERCENT = 0.02

MINIMUM_PRICE_ROWS_FOR_SWINGS = 5


@dataclass(frozen=True)
class SupportResistanceLevels:
    nearest_support: float | None
    nearest_resistance: float | None
    swing_low: float | None
    swing_high: float | None
    sma_20_support_or_resistance: str | None  # "SUPPORT" | "RESISTANCE" | None
    sma_50_support_or_resistance: str | None
    sma_200_support_or_resistance: str | None
    insufficient_reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "nearest_support": self.nearest_support,
            "nearest_resistance": self.nearest_resistance,
            "swing_low": self.swing_low,
            "swing_high": self.swing_high,
            "sma_20_support_or_resistance": self.sma_20_support_or_resistance,
            "sma_50_support_or_resistance": self.sma_50_support_or_resistance,
            "sma_200_support_or_resistance": self.sma_200_support_or_resistance,
            "insufficient_reasons": list(self.insufficient_reasons),
        }


@dataclass(frozen=True)
class SetupMath:
    direction: str

    entry_zone_low: float | None
    entry_zone_high: float | None

    target_price: float | None
    stop_price: float | None
    stop_method: str

    risk_per_share: float | None
    reward_per_share: float | None
    stock_risk_reward: float | None

    insufficient_reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "direction": self.direction,
            "entry_zone_low": self.entry_zone_low,
            "entry_zone_high": self.entry_zone_high,
            "target_price": self.target_price,
            "stop_price": self.stop_price,
            "stop_method": self.stop_method,
            "risk_per_share": self.risk_per_share,
            "reward_per_share": self.reward_per_share,
            "stock_risk_reward": self.stock_risk_reward,
            "insufficient_reasons": list(self.insufficient_reasons),
        }


def detect_support_resistance(
    highs: list[float],
    lows: list[float],
    current_close: float | None,
    sma_20: float | None = None,
    sma_50: float | None = None,
    sma_200: float | None = None,
    swing_window: int = 2,
) -> SupportResistanceLevels:
    """Combine swing-based and moving-average dynamic S/R into nearest levels."""
    reasons: list[str] = []

    if current_close is None:
        reasons.append("current_close is missing")
        return SupportResistanceLevels(
            nearest_support=None,
            nearest_resistance=None,
            swing_low=None,
            swing_high=None,
            sma_20_support_or_resistance=None,
            sma_50_support_or_resistance=None,
            sma_200_support_or_resistance=None,
            insufficient_reasons=reasons,
        )

    if len(lows) < MINIMUM_PRICE_ROWS_FOR_SWINGS or len(highs) < MINIMUM_PRICE_ROWS_FOR_SWINGS:
        reasons.append(
            f"need at least {MINIMUM_PRICE_ROWS_FOR_SWINGS} price rows for swing detection"
        )

    swing_low_point = latest_swing_low_below(
        lows=lows,
        reference_price=current_close,
        window=swing_window,
    )
    swing_high_point = latest_swing_high_above(
        highs=highs,
        reference_price=current_close,
        window=swing_window,
    )

    if swing_low_point is None:
        reasons.append("no swing low below current price")
    if swing_high_point is None:
        reasons.append("no swing high above current price")

    support_candidates: list[float] = []
    resistance_candidates: list[float] = []

    if swing_low_point is not None:
        support_candidates.append(swing_low_point.value)
    if swing_high_point is not None:
        resistance_candidates.append(swing_high_point.value)

    sma_20_role = _classify_sma_role(current_close, sma_20)
    sma_50_role = _classify_sma_role(current_close, sma_50)
    sma_200_role = _classify_sma_role(current_close, sma_200)

    if sma_20_role == "SUPPORT" and sma_20 is not None:
        support_candidates.append(sma_20)
    elif sma_20_role == "RESISTANCE" and sma_20 is not None:
        resistance_candidates.append(sma_20)

    if sma_50_role == "SUPPORT" and sma_50 is not None:
        support_candidates.append(sma_50)
    elif sma_50_role == "RESISTANCE" and sma_50 is not None:
        resistance_candidates.append(sma_50)

    if sma_200_role == "SUPPORT" and sma_200 is not None:
        support_candidates.append(sma_200)
    elif sma_200_role == "RESISTANCE" and sma_200 is not None:
        resistance_candidates.append(sma_200)

    nearest_support = max(support_candidates) if support_candidates else None
    nearest_resistance = (
        min(resistance_candidates) if resistance_candidates else None
    )

    if nearest_support is None:
        reasons.append("no usable support level")
    if nearest_resistance is None:
        reasons.append("no usable resistance level")

    return SupportResistanceLevels(
        nearest_support=nearest_support,
        nearest_resistance=nearest_resistance,
        swing_low=swing_low_point.value if swing_low_point else None,
        swing_high=swing_high_point.value if swing_high_point else None,
        sma_20_support_or_resistance=sma_20_role,
        sma_50_support_or_resistance=sma_50_role,
        sma_200_support_or_resistance=sma_200_role,
        insufficient_reasons=reasons,
    )


def calculate_setup_math(
    current_close: float | None,
    nearest_support: float | None,
    nearest_resistance: float | None,
    atr_14: float | None,
) -> SetupMath:
    """Compute entry zone, stop, target, R/R for a long setup.

    All math is deterministic and bounded; any missing input degrades the
    output gracefully (None fields + an explicit ``insufficient_reasons`` list)
    rather than raising or fabricating values.
    """
    reasons: list[str] = []

    if current_close is None:
        return SetupMath(
            direction=SETUP_DIRECTION_UNDEFINED,
            entry_zone_low=None,
            entry_zone_high=None,
            target_price=None,
            stop_price=None,
            stop_method=STOP_METHOD_UNDEFINED,
            risk_per_share=None,
            reward_per_share=None,
            stock_risk_reward=None,
            insufficient_reasons=["current_close is missing"],
        )

    if atr_14 is not None and atr_14 > 0:
        entry_low = current_close - ATR_ENTRY_ZONE_MULTIPLIER * atr_14
        entry_high = current_close + ATR_ENTRY_ZONE_MULTIPLIER * atr_14
        stop_price: float | None = current_close - ATR_STOP_MULTIPLIER * atr_14
        stop_method = STOP_METHOD_ATR
    elif nearest_support is not None:
        entry_low = current_close * (1.0 - FALLBACK_ENTRY_ZONE_PERCENT)
        entry_high = current_close * (1.0 + FALLBACK_ENTRY_ZONE_PERCENT)
        stop_price = nearest_support * (1.0 - SWING_LOW_STOP_BUFFER_PERCENT)
        stop_method = STOP_METHOD_SWING_LOW_BUFFER
    else:
        entry_low = None
        entry_high = None
        stop_price = None
        stop_method = STOP_METHOD_UNDEFINED
        reasons.append("no ATR and no support level — cannot compute stop")

    target_price = nearest_resistance if nearest_resistance is not None else None
    if target_price is None:
        reasons.append("no resistance level — cannot compute target")

    risk_per_share: float | None = None
    reward_per_share: float | None = None
    stock_risk_reward: float | None = None

    if stop_price is not None and stop_price < current_close:
        risk_per_share = current_close - stop_price

    if target_price is not None and target_price > current_close:
        reward_per_share = target_price - current_close

    if (
        risk_per_share is not None
        and risk_per_share > 0
        and reward_per_share is not None
        and reward_per_share > 0
    ):
        stock_risk_reward = reward_per_share / risk_per_share

    direction = SETUP_DIRECTION_LONG
    if (
        stop_price is None
        or target_price is None
        or risk_per_share is None
        or risk_per_share <= 0
    ):
        direction = SETUP_DIRECTION_UNDEFINED

    return SetupMath(
        direction=direction,
        entry_zone_low=entry_low,
        entry_zone_high=entry_high,
        target_price=target_price,
        stop_price=stop_price,
        stop_method=stop_method,
        risk_per_share=risk_per_share,
        reward_per_share=reward_per_share,
        stock_risk_reward=stock_risk_reward,
        insufficient_reasons=reasons,
    )


def _classify_sma_role(
    current_close: float | None,
    sma_value: float | None,
) -> str | None:
    """An SMA below current price acts as dynamic support; above it acts as
    dynamic resistance. Returns None when either input is missing or equal.
    """
    if current_close is None or sma_value is None:
        return None
    if sma_value < current_close:
        return "SUPPORT"
    if sma_value > current_close:
        return "RESISTANCE"
    return None


__all__ = [
    "ATR_ENTRY_ZONE_MULTIPLIER",
    "ATR_STOP_MULTIPLIER",
    "FALLBACK_ENTRY_ZONE_PERCENT",
    "MINIMUM_PRICE_ROWS_FOR_SWINGS",
    "SETUP_DIRECTION_LONG",
    "SETUP_DIRECTION_UNDEFINED",
    "STOP_METHOD_ATR",
    "STOP_METHOD_SWING_LOW_BUFFER",
    "STOP_METHOD_UNDEFINED",
    "SWING_LOW_STOP_BUFFER_PERCENT",
    "SetupMath",
    "SupportResistanceLevels",
    "calculate_setup_math",
    "detect_support_resistance",
]
