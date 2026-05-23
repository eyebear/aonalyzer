import math

from app.quant.support_resistance import (
    SETUP_DIRECTION_LONG,
    SETUP_DIRECTION_UNDEFINED,
    STOP_METHOD_ATR,
    STOP_METHOD_SWING_LOW_BUFFER,
    STOP_METHOD_UNDEFINED,
    calculate_setup_math,
    detect_support_resistance,
)


def _v_pattern_lows() -> list[float]:
    return [10.0, 9.0, 8.0, 7.0, 8.0, 9.0, 10.0, 11.0, 12.0, 11.5]


def _inverted_v_highs() -> list[float]:
    return [10.5, 11.0, 12.0, 13.0, 14.0, 13.0, 12.5, 12.0, 11.0, 10.5]


def test_detect_support_resistance_basic_swing_low_and_high() -> None:
    levels = detect_support_resistance(
        highs=_inverted_v_highs(),
        lows=_v_pattern_lows(),
        current_close=11.0,
        swing_window=2,
    )

    assert levels.swing_low == 7.0
    assert levels.swing_high == 14.0
    assert levels.nearest_support == 7.0
    assert levels.nearest_resistance == 14.0


def test_detect_support_resistance_picks_higher_support_from_sma_50() -> None:
    levels = detect_support_resistance(
        highs=_inverted_v_highs(),
        lows=_v_pattern_lows(),
        current_close=11.0,
        sma_50=10.0,  # below current → dynamic support, higher than swing low (7)
        swing_window=2,
    )

    assert levels.swing_low == 7.0
    assert levels.nearest_support == 10.0
    assert levels.sma_50_support_or_resistance == "SUPPORT"


def test_detect_support_resistance_picks_lower_resistance_from_sma_50() -> None:
    levels = detect_support_resistance(
        highs=_inverted_v_highs(),
        lows=_v_pattern_lows(),
        current_close=11.0,
        sma_50=13.0,  # above current → dynamic resistance, lower than swing high (14)
        swing_window=2,
    )

    assert levels.nearest_resistance == 13.0
    assert levels.sma_50_support_or_resistance == "RESISTANCE"


def test_detect_support_resistance_returns_reasons_when_inputs_thin() -> None:
    levels = detect_support_resistance(
        highs=[10.0, 11.0, 12.0],
        lows=[9.0, 8.0, 9.0],
        current_close=10.0,
        swing_window=2,
    )

    assert (
        levels.nearest_support is None
        or "no swing low below current price" in levels.insufficient_reasons
    )
    assert any("need at least" in r for r in levels.insufficient_reasons)


def test_detect_support_resistance_missing_current_close_short_circuits() -> None:
    levels = detect_support_resistance(
        highs=_inverted_v_highs(),
        lows=_v_pattern_lows(),
        current_close=None,
    )
    assert levels.nearest_support is None
    assert levels.nearest_resistance is None
    assert "current_close is missing" in levels.insufficient_reasons


def test_setup_math_with_atr_uses_atr_stop_and_entry_zone() -> None:
    setup = calculate_setup_math(
        current_close=100.0,
        nearest_support=95.0,
        nearest_resistance=110.0,
        atr_14=2.0,
    )

    # ATR_STOP_MULTIPLIER=1.5 → stop = 100 - 3 = 97
    # ATR_ENTRY_ZONE_MULTIPLIER=0.5 → entry_zone = [99, 101]
    assert setup.stop_method == STOP_METHOD_ATR
    assert math.isclose(setup.stop_price or 0, 97.0, abs_tol=1e-9)
    assert math.isclose(setup.entry_zone_low or 0, 99.0, abs_tol=1e-9)
    assert math.isclose(setup.entry_zone_high or 0, 101.0, abs_tol=1e-9)
    assert setup.target_price == 110.0
    assert math.isclose(setup.risk_per_share or 0, 3.0, abs_tol=1e-9)
    assert math.isclose(setup.reward_per_share or 0, 10.0, abs_tol=1e-9)
    assert math.isclose(setup.stock_risk_reward or 0, 10.0 / 3.0, rel_tol=1e-9)
    assert setup.direction == SETUP_DIRECTION_LONG


def test_setup_math_falls_back_to_swing_low_buffer_when_no_atr() -> None:
    setup = calculate_setup_math(
        current_close=100.0,
        nearest_support=95.0,
        nearest_resistance=110.0,
        atr_14=None,
    )

    # Swing low buffer = 2% below 95 = 93.1
    assert setup.stop_method == STOP_METHOD_SWING_LOW_BUFFER
    assert math.isclose(setup.stop_price or 0, 93.1, abs_tol=1e-9)
    # Fallback entry zone = ±2% around current
    assert math.isclose(setup.entry_zone_low or 0, 98.0, abs_tol=1e-9)
    assert math.isclose(setup.entry_zone_high or 0, 102.0, abs_tol=1e-9)
    assert setup.target_price == 110.0
    assert setup.direction == SETUP_DIRECTION_LONG


def test_setup_math_undefined_when_no_atr_and_no_support() -> None:
    setup = calculate_setup_math(
        current_close=100.0,
        nearest_support=None,
        nearest_resistance=110.0,
        atr_14=None,
    )

    assert setup.stop_method == STOP_METHOD_UNDEFINED
    assert setup.stop_price is None
    assert setup.direction == SETUP_DIRECTION_UNDEFINED
    assert any("no ATR and no support level" in r for r in setup.insufficient_reasons)


def test_setup_math_no_resistance_means_no_target() -> None:
    setup = calculate_setup_math(
        current_close=100.0,
        nearest_support=95.0,
        nearest_resistance=None,
        atr_14=2.0,
    )

    assert setup.target_price is None
    assert setup.reward_per_share is None
    assert setup.stock_risk_reward is None
    assert setup.direction == SETUP_DIRECTION_UNDEFINED
    assert any("no resistance level" in r for r in setup.insufficient_reasons)


def test_setup_math_handles_missing_current_close() -> None:
    setup = calculate_setup_math(
        current_close=None,
        nearest_support=95.0,
        nearest_resistance=110.0,
        atr_14=2.0,
    )
    assert setup.direction == SETUP_DIRECTION_UNDEFINED
    assert setup.stop_method == STOP_METHOD_UNDEFINED
    assert setup.entry_zone_low is None
    assert setup.target_price is None


def test_setup_math_risk_reward_uses_only_positive_components() -> None:
    # Stop above current: risk should be None (already invalid).
    setup = calculate_setup_math(
        current_close=100.0,
        nearest_support=110.0,  # support above current is nonsensical but allowed
        nearest_resistance=105.0,
        atr_14=None,
    )
    # SWING_LOW_BUFFER stop = 110 * 0.98 = 107.8, which is above current (100).
    # risk_per_share should be None because stop_price < current_close fails.
    assert setup.risk_per_share is None
    assert setup.direction == SETUP_DIRECTION_UNDEFINED
