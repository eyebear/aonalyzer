import math

from app.iv_history.iv_percentile_calculator import calculate_iv_percentile
from app.iv_history.iv_rank_calculator import calculate_iv_rank


def test_iv_rank_returns_none_when_history_too_small() -> None:
    history = [0.2] * 29  # below the 30-day minimum
    assert calculate_iv_rank(current_iv=0.3, historical_ivs=history) is None


def test_iv_rank_returns_none_when_current_iv_missing() -> None:
    history = [0.1 + i * 0.001 for i in range(60)]
    assert calculate_iv_rank(current_iv=None, historical_ivs=history) is None


def test_iv_rank_clamps_to_zero_and_hundred() -> None:
    history = [0.20 + (i % 10) * 0.01 for i in range(60)]  # min=0.20, max=0.29
    assert calculate_iv_rank(current_iv=0.10, historical_ivs=history) == 0.0
    assert calculate_iv_rank(current_iv=0.50, historical_ivs=history) == 100.0


def test_iv_rank_basic_midpoint() -> None:
    # min=0.10, max=0.30, current 0.20 → 50% rank.
    history = [0.10, 0.30] + [0.15] * 28
    rank = calculate_iv_rank(
        current_iv=0.20,
        historical_ivs=history,
        minimum_history_days=30,
    )
    assert rank is not None
    assert math.isclose(rank, 50.0, abs_tol=1e-9)


def test_iv_rank_returns_50_when_history_flat() -> None:
    history = [0.25] * 60
    # max == min → return 50.0 (only-known level)
    assert calculate_iv_rank(current_iv=0.25, historical_ivs=history) == 50.0


def test_iv_percentile_returns_none_when_history_too_small() -> None:
    history = [0.2] * 29
    assert calculate_iv_percentile(current_iv=0.3, historical_ivs=history) is None


def test_iv_percentile_basic() -> None:
    history = [0.10] * 30 + [0.30] * 30  # 60 rows
    # current=0.20 → 30 of 60 below → 50.0
    assert calculate_iv_percentile(
        current_iv=0.20,
        historical_ivs=history,
        minimum_history_days=30,
    ) == 50.0


def test_iv_percentile_zero_and_hundred() -> None:
    history = [0.15 + (i % 10) * 0.001 for i in range(60)]
    assert calculate_iv_percentile(current_iv=0.05, historical_ivs=history) == 0.0
    assert calculate_iv_percentile(current_iv=0.99, historical_ivs=history) == 100.0


def test_iv_percentile_ignores_non_positive_history() -> None:
    history = [0.0, -0.1, None] * 10 + [0.20] * 40
    # After cleaning, only 40 valid rows; with minimum=30 that's enough.
    result = calculate_iv_percentile(
        current_iv=0.30,
        historical_ivs=history,
        minimum_history_days=30,
    )
    assert result == 100.0
