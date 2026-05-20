from app.setup_detection.setup_detector import (
    DIRECTION_LONG,
    DIRECTION_NONE,
    DIRECTION_SHORT,
    DIRECTION_WATCH,
    INSUFFICIENT_INPUT,
    SETUP_BREAKDOWN_SHORT,
    SETUP_BREAKOUT_RETEST_LONG,
    SETUP_NO_TRADE,
    SETUP_OVERSOLD_BOUNCE_WATCH,
    SETUP_PULLBACK_LONG,
    SETUP_SECTOR_STRENGTH_LONG,
    SUFFICIENT,
    SetupInputs,
    detect_setup,
)


def test_pullback_long() -> None:
    result = detect_setup(
        SetupInputs(
            close=104.0,
            sma_20=105.0,
            sma_50=100.0,
            sma_200=90.0,
            rsi_14=45.0,
            atr_14=4.0,
            volume_ratio=1.5,
            nearest_resistance=None,
            risk_reward=3.0,
            regime_label="RISK_ON",
        )
    )
    assert result.setup_type == SETUP_PULLBACK_LONG
    assert result.direction == DIRECTION_LONG
    assert result.data_sufficiency_status == SUFFICIENT
    # base 50 + rr 10 + trend 10 + volume 5 + regime 10
    assert result.score == 85


def test_breakout_retest_long() -> None:
    result = detect_setup(
        SetupInputs(
            close=120.0,
            sma_20=105.0,
            sma_50=100.0,
            sma_200=90.0,
            rsi_14=60.0,
            atr_14=4.0,
            volume_ratio=1.0,
            nearest_resistance=120.0,
            risk_reward=1.5,
            regime_label="NEUTRAL",
        )
    )
    assert result.setup_type == SETUP_BREAKOUT_RETEST_LONG
    assert result.direction == DIRECTION_LONG
    # base 50 + trend 10 (no rr, no volume, neutral regime)
    assert result.score == 60


def test_sector_strength_long() -> None:
    result = detect_setup(
        SetupInputs(
            close=120.0,
            sma_20=105.0,
            sma_50=100.0,
            sma_200=90.0,
            rsi_14=60.0,
            atr_14=4.0,
            nearest_resistance=None,  # not a breakout retest
            regime_label="RISK_ON",
            sector_trend="OUTPERFORM",
            sector_rs_rank=1,
        )
    )
    assert result.setup_type == SETUP_SECTOR_STRENGTH_LONG
    assert result.direction == DIRECTION_LONG
    # base 45 + trend 10 + regime 10 + sector 5
    assert result.score == 70


def test_breakdown_short() -> None:
    result = detect_setup(
        SetupInputs(
            close=95.0,
            sma_20=98.0,
            sma_50=100.0,
            sma_200=110.0,
            rsi_14=45.0,
            macd_histogram=-1.0,
            volume_ratio=1.3,
            nearest_support=96.0,
            risk_reward=2.5,
            regime_label="RISK_OFF",
        )
    )
    assert result.setup_type == SETUP_BREAKDOWN_SHORT
    assert result.direction == DIRECTION_SHORT
    # base 45 + rr 10 + trend 10 + volume 5 + regime 10
    assert result.score == 80


def test_oversold_bounce_watch_not_shorted() -> None:
    # Downtrend AND breaking support, but oversold -> WATCH, not BREAKDOWN_SHORT.
    result = detect_setup(
        SetupInputs(
            close=90.0,
            sma_20=95.0,
            sma_50=100.0,
            rsi_14=25.0,
            macd_histogram=-1.0,
            nearest_support=96.0,
            bollinger_lower=92.0,
        )
    )
    assert result.setup_type == SETUP_OVERSOLD_BOUNCE_WATCH
    assert result.direction == DIRECTION_WATCH
    # base 30 + below_lower_band 5
    assert result.score == 35


def test_no_trade_when_sideways() -> None:
    result = detect_setup(
        SetupInputs(close=100.0, sma_20=100.0, sma_50=100.0, rsi_14=50.0)
    )
    assert result.setup_type == SETUP_NO_TRADE
    assert result.direction == DIRECTION_NONE
    assert result.score == 0


def test_insufficient_input_when_core_missing() -> None:
    result = detect_setup(SetupInputs(close=None, sma_20=None, sma_50=None))
    assert result.setup_type == SETUP_NO_TRADE
    assert result.data_sufficiency_status == INSUFFICIENT_INPUT
    assert result.score == 0


def test_risk_off_penalizes_long_score() -> None:
    base = dict(
        close=104.0,
        sma_20=105.0,
        sma_50=100.0,
        sma_200=90.0,
        rsi_14=45.0,
        atr_14=4.0,
        risk_reward=3.0,
    )
    risk_on = detect_setup(SetupInputs(regime_label="RISK_ON", **base))
    risk_off = detect_setup(SetupInputs(regime_label="RISK_OFF", **base))
    assert risk_on.setup_type == SETUP_PULLBACK_LONG
    assert risk_off.setup_type == SETUP_PULLBACK_LONG
    # RISK_ON adds +10, RISK_OFF subtracts -10 => 20-point spread.
    assert risk_on.score - risk_off.score == 20
