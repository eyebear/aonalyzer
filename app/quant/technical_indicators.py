from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MacdResult:
    macd: float | None
    signal: float | None
    histogram: float | None

    def to_dict(self) -> dict[str, float | None]:
        return {
            "macd": self.macd,
            "signal": self.signal,
            "histogram": self.histogram,
        }


@dataclass(frozen=True)
class BollingerBandsResult:
    upper: float | None
    middle: float | None
    lower: float | None

    def to_dict(self) -> dict[str, float | None]:
        return {
            "upper": self.upper,
            "middle": self.middle,
            "lower": self.lower,
        }


def simple_moving_average(closes: list[float], period: int) -> float | None:
    """SMA of the most recent ``period`` closes. Returns None when not enough data."""
    if period < 1 or len(closes) < period:
        return None

    window = closes[-period:]
    return sum(window) / period


def exponential_moving_average(closes: list[float], period: int) -> float | None:
    """EMA seeded by SMA of the first ``period`` closes (TradingView convention)."""
    if period < 1 or len(closes) < period:
        return None

    alpha = 2.0 / (period + 1)

    ema = sum(closes[:period]) / period

    for value in closes[period:]:
        ema = (value - ema) * alpha + ema

    return ema


def _exponential_moving_average_series(
    values: list[float],
    period: int,
) -> list[float]:
    """Internal helper that returns the entire EMA series after seeding."""
    if period < 1 or len(values) < period:
        return []

    alpha = 2.0 / (period + 1)
    seed = sum(values[:period]) / period

    series: list[float] = [seed]
    for value in values[period:]:
        next_ema = (value - series[-1]) * alpha + series[-1]
        series.append(next_ema)

    return series


def relative_strength_index(closes: list[float], period: int = 14) -> float | None:
    """Wilder's RSI. Needs ``period + 1`` closes."""
    if period < 1 or len(closes) < period + 1:
        return None

    gains_sum = 0.0
    losses_sum = 0.0

    for index in range(1, period + 1):
        change = closes[index] - closes[index - 1]
        if change >= 0:
            gains_sum += change
        else:
            losses_sum += -change

    avg_gain = gains_sum / period
    avg_loss = losses_sum / period

    for index in range(period + 1, len(closes)):
        change = closes[index] - closes[index - 1]
        gain = max(change, 0.0)
        loss = -min(change, 0.0)

        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def moving_average_convergence_divergence(
    closes: list[float],
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
) -> MacdResult:
    """Standard MACD. macd = EMA(fast) - EMA(slow); signal = EMA(macd_series, signal)."""
    if (
        fast_period < 1
        or slow_period <= fast_period
        or signal_period < 1
        or len(closes) < slow_period
    ):
        return MacdResult(macd=None, signal=None, histogram=None)

    fast_series = _exponential_moving_average_series(closes, fast_period)
    slow_series = _exponential_moving_average_series(closes, slow_period)

    if not fast_series or not slow_series:
        return MacdResult(macd=None, signal=None, histogram=None)

    # Align: fast_series starts at index fast_period-1, slow_series at slow_period-1.
    # We only want the overlapping tail where both EMAs exist.
    overlap_length = min(
        len(fast_series),
        len(slow_series),
    )
    if overlap_length < 1:
        return MacdResult(macd=None, signal=None, histogram=None)

    fast_tail = fast_series[-overlap_length:]
    slow_tail = slow_series[-overlap_length:]

    macd_series = [fast - slow for fast, slow in zip(fast_tail, slow_tail)]
    macd_value = macd_series[-1]

    if len(macd_series) < signal_period:
        return MacdResult(macd=macd_value, signal=None, histogram=None)

    signal_series = _exponential_moving_average_series(macd_series, signal_period)
    if not signal_series:
        return MacdResult(macd=macd_value, signal=None, histogram=None)

    signal_value = signal_series[-1]
    histogram_value = macd_value - signal_value

    return MacdResult(macd=macd_value, signal=signal_value, histogram=histogram_value)


def average_true_range(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    period: int = 14,
) -> float | None:
    """Wilder's ATR. Needs at least ``period + 1`` rows of OHLC."""
    if period < 1:
        return None

    length = len(closes)
    if len(highs) != length or len(lows) != length:
        return None

    if length < period + 1:
        return None

    true_ranges: list[float] = []
    for index in range(1, length):
        high = highs[index]
        low = lows[index]
        previous_close = closes[index - 1]

        true_range = max(
            high - low,
            abs(high - previous_close),
            abs(low - previous_close),
        )
        true_ranges.append(true_range)

    if len(true_ranges) < period:
        return None

    atr = sum(true_ranges[:period]) / period
    for true_range in true_ranges[period:]:
        atr = (atr * (period - 1) + true_range) / period

    return atr


def bollinger_bands(
    closes: list[float],
    period: int = 20,
    num_stddev: float = 2.0,
) -> BollingerBandsResult:
    """Bollinger Bands using population standard deviation (TradingView convention)."""
    if period < 1 or len(closes) < period:
        return BollingerBandsResult(upper=None, middle=None, lower=None)

    window = closes[-period:]
    middle = sum(window) / period

    squared_deviations = [(value - middle) ** 2 for value in window]
    variance = sum(squared_deviations) / period
    stddev = math.sqrt(variance)

    upper = middle + num_stddev * stddev
    lower = middle - num_stddev * stddev

    return BollingerBandsResult(upper=upper, middle=middle, lower=lower)


def volume_ratio(volumes: list[float], period: int = 20) -> float | None:
    """Latest volume divided by SMA(volume, period). Returns None on insufficient data."""
    if period < 1 or len(volumes) < period:
        return None

    average_volume = sum(volumes[-period:]) / period

    if average_volume == 0:
        return None

    return volumes[-1] / average_volume


def required_history_for_indicators() -> dict[str, int]:
    """Minimum number of daily-price rows required for each indicator."""
    return {
        "sma_20": 20,
        "sma_50": 50,
        "sma_200": 200,
        "ema_12": 12,
        "ema_26": 26,
        "rsi_14": 15,
        "macd": 26,
        "macd_signal": 26 + 9 - 1,  # 34
        "atr_14": 15,
        "bollinger_bands_20": 20,
        "volume_ratio_20": 20,
    }


def minimum_rows_for_any_indicator() -> int:
    """The smallest row count that lets at least one indicator compute."""
    return min(required_history_for_indicators().values())


def _all_numeric(values: list[Any]) -> bool:
    for value in values:
        if value is None:
            return False
        if not isinstance(value, (int, float)):
            return False
        if isinstance(value, float) and math.isnan(value):
            return False
    return True


__all__ = [
    "BollingerBandsResult",
    "MacdResult",
    "average_true_range",
    "bollinger_bands",
    "exponential_moving_average",
    "minimum_rows_for_any_indicator",
    "moving_average_convergence_divergence",
    "relative_strength_index",
    "required_history_for_indicators",
    "simple_moving_average",
    "volume_ratio",
]
