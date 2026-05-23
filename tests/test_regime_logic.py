from app.market_regime.regime_logic import (
    REGIME_NEUTRAL,
    REGIME_RISK_OFF,
    REGIME_RISK_ON,
    TREND_DOWN,
    TREND_INSUFFICIENT,
    TREND_SIDEWAYS,
    TREND_UP,
    VIX_CALM,
    VIX_NORMAL,
    VIX_STRESSED,
    VIX_UNKNOWN,
    YIELD_FALLING,
    YIELD_RISING,
    YIELD_STABLE,
    YIELD_UNKNOWN,
    classify_trend,
    classify_vix,
    classify_yield_pressure,
    composite_regime,
)


def test_classify_trend_up() -> None:
    closes = [float(x) for x in range(100, 110)]  # strictly increasing, 10 rows
    result = classify_trend(closes, fast_period=2, slow_period=3, min_rows=3)
    assert result.trend == TREND_UP
    assert result.last_close == 109.0


def test_classify_trend_down() -> None:
    closes = [float(x) for x in range(110, 100, -1)]  # strictly decreasing
    result = classify_trend(closes, fast_period=2, slow_period=3, min_rows=3)
    assert result.trend == TREND_DOWN


def test_classify_trend_sideways() -> None:
    # last_close (102) > slow SMA (100.667) but fast SMA (98.5) < slow SMA,
    # so neither the UP nor DOWN condition holds -> SIDEWAYS.
    closes = [100.0, 105.0, 95.0, 102.0]
    result = classify_trend(closes, fast_period=2, slow_period=3, min_rows=3)
    assert result.trend == TREND_SIDEWAYS


def test_classify_trend_insufficient() -> None:
    result = classify_trend([100.0, 101.0], fast_period=2, slow_period=3, min_rows=3)
    assert result.trend == TREND_INSUFFICIENT
    assert result.reason is not None


def test_classify_vix_bands() -> None:
    assert classify_vix(12.0, 15.0, 25.0) == VIX_CALM
    assert classify_vix(15.0, 15.0, 25.0) == VIX_CALM
    assert classify_vix(20.0, 15.0, 25.0) == VIX_NORMAL
    assert classify_vix(25.0, 15.0, 25.0) == VIX_STRESSED
    assert classify_vix(40.0, 15.0, 25.0) == VIX_STRESSED
    assert classify_vix(None, 15.0, 25.0) == VIX_UNKNOWN


def test_classify_yield_rising_triggers_pressure() -> None:
    # +25% over a 2-day lookback (4.0 -> 5.0); rise_pct=0.10
    result = classify_yield_pressure(
        [4.0, 4.5, 5.0], lookback_days=2, pressure_level=99.0, rise_pct=0.10
    )
    assert result.state == YIELD_RISING
    assert result.pressure is True
    assert result.level == 5.0


def test_classify_yield_level_triggers_pressure_even_if_stable() -> None:
    result = classify_yield_pressure(
        [4.6, 4.6, 4.6], lookback_days=2, pressure_level=4.5, rise_pct=0.10
    )
    assert result.state == YIELD_STABLE
    assert result.pressure is True  # level >= pressure_level


def test_classify_yield_falling_no_pressure() -> None:
    result = classify_yield_pressure(
        [5.0, 4.5, 4.0], lookback_days=2, pressure_level=4.5, rise_pct=0.10
    )
    assert result.state == YIELD_FALLING
    assert result.pressure is False


def test_classify_yield_insufficient() -> None:
    result = classify_yield_pressure([4.0], lookback_days=2, pressure_level=4.5, rise_pct=0.10)
    assert result.state == YIELD_UNKNOWN
    assert result.pressure is False
    assert result.reason is not None


def test_composite_regime_risk_on() -> None:
    result = composite_regime(TREND_UP, TREND_UP, TREND_UP, VIX_CALM, yield_pressure=False)
    assert result.regime_label == REGIME_RISK_ON
    assert result.regime_score == 4
    assert result.uptrend_count == 3
    assert result.downtrend_count == 0


def test_composite_regime_risk_off() -> None:
    result = composite_regime(TREND_DOWN, TREND_DOWN, TREND_DOWN, VIX_STRESSED, yield_pressure=True)
    assert result.regime_label == REGIME_RISK_OFF
    assert result.regime_score == -5
    assert result.downtrend_count == 3


def test_composite_regime_neutral_mixed() -> None:
    # +1 (spy up) -1 (qqq down) +0 (iwm sideways) +0 (vix normal) -1 (yield) = -1
    result = composite_regime(TREND_UP, TREND_DOWN, TREND_SIDEWAYS, VIX_NORMAL, yield_pressure=True)
    assert result.regime_label == REGIME_NEUTRAL
    assert result.regime_score == -1


def test_composite_regime_ignores_insufficient_trends() -> None:
    # Only QQQ up counts; everything else neutral → score 1 → NEUTRAL
    result = composite_regime(
        TREND_INSUFFICIENT, TREND_UP, TREND_INSUFFICIENT, VIX_UNKNOWN, yield_pressure=False
    )
    assert result.regime_label == REGIME_NEUTRAL
    assert result.regime_score == 1
    assert result.uptrend_count == 1
