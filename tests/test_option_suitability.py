from app.options.iv_analysis import IV_TOO_HIGH
from app.options.option_filters import (
    DTE_TOO_SHORT,
    LOW_OPEN_INTEREST,
    OPTION_TOO_EXPENSIVE,
    SPREAD_TOO_WIDE,
)
from app.options.option_suitability import (
    MANUAL_OPTION_INPUT_NEEDED,
    OPTION_ANALYSIS_SKIPPED,
    OPTION_DATA_NOT_AVAILABLE,
    OPTION_SUITABLE,
    STOCK_OK_BUT_OPTION_BAD,
    OptionFields,
    OptionThresholds,
    StockContext,
    evaluate_option_suitability,
)
from app.options.target_breakeven import (
    BREAKEVEN_TOO_FAR,
    TARGET_BELOW_BREAKEVEN,
    TARGET_MARGIN_TOO_THIN,
)

THRESHOLDS = OptionThresholds()


def _good_call(**overrides) -> OptionFields:
    base = dict(
        option_type="CALL",
        strike=100.0,
        dte=60,
        bid=4.9,
        ask=5.1,
        last_price=5.0,
        volume=500,
        open_interest=2000,
        implied_volatility=0.50,
        underlying_price=100.0,
    )
    base.update(overrides)
    return OptionFields(**base)


def test_option_suitable() -> None:
    result = evaluate_option_suitability(
        _good_call(), THRESHOLDS, StockContext(target_price=120.0, underlying_price=100.0)
    )
    assert result.suitability_label == OPTION_SUITABLE
    assert result.is_suitable is True
    assert result.rejection_labels == []
    assert result.breakeven == 105.0
    assert result.data_sufficiency_status == "SUFFICIENT"


def test_no_option_data_returns_not_available() -> None:
    result = evaluate_option_suitability(OptionFields(), THRESHOLDS)
    assert result.suitability_label == OPTION_DATA_NOT_AVAILABLE
    assert result.is_suitable is False


def test_no_option_data_but_requested_needs_input() -> None:
    result = evaluate_option_suitability(OptionFields(), THRESHOLDS, option_input_requested=True)
    assert result.suitability_label == MANUAL_OPTION_INPUT_NEEDED


def test_disabled_returns_analysis_skipped() -> None:
    result = evaluate_option_suitability(_good_call(), THRESHOLDS, enabled=False)
    assert result.suitability_label == OPTION_ANALYSIS_SKIPPED


def test_data_present_but_unevaluable_needs_input() -> None:
    # Only volume present (soft preference); no hard filter can run.
    result = evaluate_option_suitability(OptionFields(volume=100), THRESHOLDS)
    assert result.suitability_label == MANUAL_OPTION_INPUT_NEEDED


def test_option_too_expensive() -> None:
    result = evaluate_option_suitability(
        _good_call(bid=11.9, ask=12.1, last_price=12.0),
        THRESHOLDS,
        StockContext(target_price=200.0, underlying_price=100.0),
    )
    assert result.suitability_label == STOCK_OK_BUT_OPTION_BAD
    assert OPTION_TOO_EXPENSIVE in result.rejection_labels


def test_dte_too_short() -> None:
    result = evaluate_option_suitability(
        _good_call(dte=30), THRESHOLDS, StockContext(target_price=120.0, underlying_price=100.0)
    )
    assert result.suitability_label == STOCK_OK_BUT_OPTION_BAD
    assert DTE_TOO_SHORT in result.rejection_labels


def test_spread_too_wide() -> None:
    result = evaluate_option_suitability(
        _good_call(bid=4.0, ask=6.0),
        THRESHOLDS,
        StockContext(target_price=120.0, underlying_price=100.0),
    )
    assert SPREAD_TOO_WIDE in result.rejection_labels


def test_low_open_interest() -> None:
    result = evaluate_option_suitability(
        _good_call(open_interest=50),
        THRESHOLDS,
        StockContext(target_price=120.0, underlying_price=100.0),
    )
    assert LOW_OPEN_INTEREST in result.rejection_labels


def test_iv_too_high() -> None:
    result = evaluate_option_suitability(
        _good_call(implied_volatility=0.90),
        THRESHOLDS,
        StockContext(target_price=120.0, underlying_price=100.0),
    )
    assert IV_TOO_HIGH in result.rejection_labels


def test_breakeven_too_far() -> None:
    # strike 110, premium 5 -> breakeven 115, spot 100 -> 15% > 12% max
    result = evaluate_option_suitability(
        _good_call(strike=110.0),
        THRESHOLDS,
        StockContext(target_price=130.0, underlying_price=100.0),
    )
    assert BREAKEVEN_TOO_FAR in result.rejection_labels


def test_target_below_breakeven() -> None:
    # breakeven 105, target 100 (below) -> reject
    result = evaluate_option_suitability(
        _good_call(),
        THRESHOLDS,
        StockContext(target_price=100.0, underlying_price=100.0),
    )
    assert TARGET_BELOW_BREAKEVEN in result.rejection_labels


def test_target_margin_too_thin() -> None:
    # breakeven 105, target 106 -> ~0.95% margin < 3% minimum
    result = evaluate_option_suitability(
        _good_call(),
        THRESHOLDS,
        StockContext(target_price=106.0, underlying_price=100.0),
    )
    assert TARGET_MARGIN_TOO_THIN in result.rejection_labels


def test_low_volume_is_warning_not_rejection() -> None:
    result = evaluate_option_suitability(
        _good_call(volume=2), THRESHOLDS, StockContext(target_price=120.0, underlying_price=100.0)
    )
    # Still suitable; LOW_VOLUME is only a warning.
    assert result.suitability_label == OPTION_SUITABLE
    assert "LOW_VOLUME" in result.warning_labels
