import math

from app.quant.technical_indicators import (
    average_true_range,
    bollinger_bands,
    exponential_moving_average,
    minimum_rows_for_any_indicator,
    moving_average_convergence_divergence,
    relative_strength_index,
    required_history_for_indicators,
    simple_moving_average,
    volume_ratio,
)


def test_simple_moving_average_known_value() -> None:
    assert simple_moving_average([1.0, 2.0, 3.0, 4.0, 5.0], 3) == (3 + 4 + 5) / 3


def test_simple_moving_average_returns_none_when_insufficient() -> None:
    assert simple_moving_average([1.0, 2.0], 3) is None
    assert simple_moving_average([], 1) is None


def test_exponential_moving_average_tradingview_seed() -> None:
    """EMA seeded by SMA of first ``period`` values, then standard recurrence."""
    closes = [1.0, 2.0, 3.0, 4.0, 5.0]
    # seed at index 2 = SMA(1,2,3) = 2.0; alpha = 2/(3+1) = 0.5
    # ema[3] = (4-2)*0.5 + 2 = 3.0
    # ema[4] = (5-3)*0.5 + 3 = 4.0
    assert exponential_moving_average(closes, 3) == 4.0


def test_exponential_moving_average_returns_none_when_insufficient() -> None:
    assert exponential_moving_average([1.0, 2.0], 3) is None


def test_rsi_returns_100_when_only_gains() -> None:
    # Monotonic up — avg_loss is 0, RSI must be 100 exactly.
    closes = [float(i) for i in range(1, 17)]
    assert relative_strength_index(closes, 14) == 100.0


def test_rsi_returns_zero_when_only_losses() -> None:
    closes = [float(i) for i in range(16, 0, -1)]
    rsi = relative_strength_index(closes, 14)
    assert rsi == 0.0


def test_rsi_returns_none_when_insufficient() -> None:
    closes = [float(i) for i in range(1, 15)]  # only 14 rows, need 15
    assert relative_strength_index(closes, 14) is None


def test_rsi_balanced_oscillation_returns_around_50() -> None:
    # Alternating +1 / -1 yields equal average gain and loss
    closes = [100.0]
    for index in range(40):
        closes.append(closes[-1] + (1 if index % 2 == 0 else -1))
    rsi = relative_strength_index(closes, 14)
    assert rsi is not None
    assert 30.0 <= rsi <= 70.0  # tightly bounded


def test_macd_returns_none_when_insufficient_for_macd_line() -> None:
    closes = [float(i) for i in range(1, 26)]  # only 25 rows, need 26
    result = moving_average_convergence_divergence(closes)
    assert result.macd is None
    assert result.signal is None
    assert result.histogram is None


def test_macd_returns_macd_but_no_signal_when_signal_period_short() -> None:
    # Exactly 26 rows: macd_line has length 1; signal needs >= 9 → None
    closes = [float(i) for i in range(1, 27)]
    result = moving_average_convergence_divergence(closes)
    assert result.macd is not None
    assert result.signal is None
    assert result.histogram is None


def test_macd_returns_all_fields_with_enough_history_and_positive_trend() -> None:
    closes = [float(i) for i in range(1, 60)]  # 59 rows, fully sufficient
    result = moving_average_convergence_divergence(closes)
    assert result.macd is not None
    assert result.signal is not None
    assert result.histogram is not None
    # Monotonic up → MACD line should be positive
    assert result.macd > 0


def test_atr_returns_none_when_insufficient() -> None:
    highs = [10.0] * 14
    lows = [9.0] * 14
    closes = [9.5] * 14
    assert average_true_range(highs, lows, closes, 14) is None


def test_atr_constant_range_equals_that_range() -> None:
    # 15 rows of identical high-low=2, previous close inside the range.
    highs = [12.0] * 15
    lows = [10.0] * 15
    closes = [11.0] * 15
    assert average_true_range(highs, lows, closes, 14) == 2.0


def test_atr_mismatched_lengths_returns_none() -> None:
    assert average_true_range([1.0, 2.0], [1.0], [1.0, 2.0], 14) is None


def test_bollinger_bands_identical_values_have_zero_width() -> None:
    closes = [50.0] * 20
    result = bollinger_bands(closes, 20, 2.0)
    assert result.middle == 50.0
    assert result.upper == 50.0
    assert result.lower == 50.0


def test_bollinger_bands_uses_population_stddev() -> None:
    # 20 values: 10x 1.0 then 10x 3.0. Mean = 2.0, population variance = 1.0.
    closes = [1.0] * 10 + [3.0] * 10
    result = bollinger_bands(closes, 20, 2.0)
    assert result.middle == 2.0
    # population stddev = 1.0, so upper = 4.0, lower = 0.0
    assert math.isclose(result.upper or 0, 4.0, rel_tol=1e-9)
    assert math.isclose(result.lower or 0, 0.0, abs_tol=1e-9)


def test_bollinger_bands_insufficient_returns_none() -> None:
    closes = [1.0] * 19
    result = bollinger_bands(closes, 20, 2.0)
    assert result.upper is None and result.middle is None and result.lower is None


def test_volume_ratio_basic() -> None:
    volumes = [100.0] * 19 + [200.0]  # SMA20=105.0, latest=200.0
    expected = 200.0 / (sum(volumes) / 20)
    assert volume_ratio(volumes, 20) == expected


def test_volume_ratio_returns_none_when_avg_is_zero() -> None:
    volumes = [0.0] * 20
    assert volume_ratio(volumes, 20) is None


def test_volume_ratio_returns_none_when_insufficient() -> None:
    volumes = [100.0] * 19
    assert volume_ratio(volumes, 20) is None


def test_required_history_table_lists_all_indicators() -> None:
    required = required_history_for_indicators()
    assert "sma_20" in required
    assert "sma_200" in required
    assert "macd_signal" in required
    assert "atr_14" in required
    assert required["sma_200"] == 200
    assert required["macd_signal"] == 34


def test_minimum_rows_for_any_indicator() -> None:
    # ema_12 needs 12, which is the smallest threshold.
    assert minimum_rows_for_any_indicator() == 12
