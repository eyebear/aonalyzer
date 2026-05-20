from app.options.breakeven import compute_breakeven
from app.options.iv_analysis import IV_TOO_HIGH, analyze_iv, normalize_iv_to_percent
from app.options.liquidity_analysis import score_liquidity
from app.options.option_filters import (
    DTE_TOO_SHORT,
    FAIL,
    LOW_OPEN_INTEREST,
    LOW_VOLUME,
    OPTION_TOO_EXPENSIVE,
    PASS,
    SKIPPED,
    SPREAD_TOO_WIDE,
    WARN,
    compute_mid,
    compute_premium,
    filter_dte,
    filter_open_interest,
    filter_premium_budget,
    filter_spread,
    volume_preference,
)


def test_compute_mid_and_premium() -> None:
    assert compute_mid(4.9, 5.1) == 5.0
    assert compute_mid(None, 5.1) is None
    assert compute_mid(6.0, 5.0) is None  # ask < bid
    assert compute_premium(4.9, 5.1, None) == 5.0
    assert compute_premium(None, None, 3.2) == 3.2
    assert compute_premium(None, None, None) is None


def test_filter_dte() -> None:
    assert filter_dte(None, 45, 90).status == SKIPPED
    out = filter_dte(30, 45, 90)
    assert out.status == FAIL and out.label == DTE_TOO_SHORT
    assert filter_dte(60, 45, 90).status == PASS


def test_filter_premium_budget() -> None:
    assert filter_premium_budget(None, 500, 1000).status == SKIPPED
    out = filter_premium_budget(12.0, 500, 1000)  # cost 1200
    assert out.status == FAIL and out.label == OPTION_TOO_EXPENSIVE
    assert filter_premium_budget(5.0, 500, 1000).status == PASS


def test_filter_spread() -> None:
    assert filter_spread(None, 5.1, 10.0).status == SKIPPED
    out = filter_spread(4.0, 6.0, 10.0)  # 40%
    assert out.status == FAIL and out.label == SPREAD_TOO_WIDE
    assert filter_spread(4.9, 5.1, 10.0).status == PASS


def test_filter_open_interest() -> None:
    assert filter_open_interest(None, 100).status == SKIPPED
    out = filter_open_interest(50, 100)
    assert out.status == FAIL and out.label == LOW_OPEN_INTEREST
    assert filter_open_interest(2000, 100).status == PASS


def test_volume_preference_is_soft() -> None:
    assert volume_preference(None, 10).status == SKIPPED
    out = volume_preference(5, 10)
    assert out.status == WARN and out.label == LOW_VOLUME
    assert not out.is_hard_fail
    assert volume_preference(100, 10).status == PASS


def test_iv_normalization_and_analysis() -> None:
    assert normalize_iv_to_percent(0.65) == 65.0
    assert normalize_iv_to_percent(65.0) == 65.0
    assert normalize_iv_to_percent(None) is None

    skipped = analyze_iv(None, warning_threshold=70, reject_threshold=85)
    assert skipped.outcome.status == SKIPPED

    high = analyze_iv(0.90, warning_threshold=70, reject_threshold=85)
    assert high.outcome.status == FAIL and high.outcome.label == IV_TOO_HIGH

    elevated = analyze_iv(0.75, warning_threshold=70, reject_threshold=85)
    assert elevated.outcome.status == WARN

    low = analyze_iv(0.40, warning_threshold=70, reject_threshold=85)
    assert low.outcome.status == PASS


def test_breakeven_call_and_put() -> None:
    assert compute_breakeven("CALL", 100.0, 5.0) == 105.0
    assert compute_breakeven("PUT", 100.0, 5.0) == 95.0
    assert compute_breakeven("CALL", None, 5.0) is None
    assert compute_breakeven(None, 100.0, 5.0) is None


def test_liquidity_score() -> None:
    assert score_liquidity(None, None, None).score is None
    good = score_liquidity(1.0, 2000, 1000, max_spread_percent=10.0)
    assert good.score is not None and good.score >= 90
    poor = score_liquidity(9.5, 10, 1, max_spread_percent=10.0)
    assert poor.score is not None and poor.score < 20
