from app.market_regime.sector_strength import (
    INSUFFICIENT_PRICE_HISTORY,
    SECTOR_INLINE,
    SECTOR_OUTPERFORM,
    SECTOR_UNDERPERFORM,
    SUFFICIENT,
    assign_ranks,
    compute_period_return,
    compute_relative_strength,
)


def test_compute_period_return_basic() -> None:
    # 100 -> 110 over a 2-day lookback = +10%
    assert compute_period_return([100.0, 105.0, 110.0], lookback_days=2) == 0.1


def test_compute_period_return_insufficient() -> None:
    assert compute_period_return([100.0], lookback_days=2) is None


def test_compute_period_return_zero_reference() -> None:
    assert compute_period_return([0.0, 1.0, 2.0], lookback_days=2) is None


def test_relative_strength_outperform() -> None:
    result = compute_relative_strength(
        sector_symbol="XLK",
        benchmark_symbol="SPY",
        sector_closes=[100.0, 110.0, 121.0],  # +21%
        benchmark_closes=[100.0, 101.0, 102.0],  # +2%
        lookback_days=2,
    )
    assert result.data_sufficiency_status == SUFFICIENT
    assert result.trend == SECTOR_OUTPERFORM
    assert abs(result.relative_strength - (0.21 - 0.02)) < 1e-9


def test_relative_strength_underperform() -> None:
    result = compute_relative_strength(
        sector_symbol="XLF",
        benchmark_symbol="SPY",
        sector_closes=[100.0, 100.0, 100.0],  # 0%
        benchmark_closes=[100.0, 101.0, 105.0],  # +5%
        lookback_days=2,
    )
    assert result.trend == SECTOR_UNDERPERFORM
    assert result.relative_strength < 0


def test_relative_strength_inline_within_band() -> None:
    result = compute_relative_strength(
        sector_symbol="XLE",
        benchmark_symbol="SPY",
        sector_closes=[100.0, 100.0, 102.0],  # +2%
        benchmark_closes=[100.0, 100.0, 102.0],  # +2%
        lookback_days=2,
        inline_band=0.005,
    )
    assert result.trend == SECTOR_INLINE
    assert result.relative_strength == 0.0


def test_relative_strength_insufficient() -> None:
    result = compute_relative_strength(
        sector_symbol="SMH",
        benchmark_symbol="SPY",
        sector_closes=[100.0],
        benchmark_closes=[100.0, 101.0, 102.0],
        lookback_days=2,
    )
    assert result.data_sufficiency_status == INSUFFICIENT_PRICE_HISTORY
    assert result.relative_strength is None
    assert result.rs_rank is None


def test_assign_ranks_orders_by_relative_strength() -> None:
    strong = compute_relative_strength(
        "XLK", "SPY", [100.0, 110.0, 130.0], [100.0, 101.0, 102.0], 2
    )
    mid = compute_relative_strength("XLF", "SPY", [100.0, 105.0, 110.0], [100.0, 101.0, 102.0], 2)
    weak = compute_relative_strength("XLE", "SPY", [100.0, 100.0, 100.0], [100.0, 101.0, 102.0], 2)
    insufficient = compute_relative_strength("SMH", "SPY", [100.0], [100.0, 101.0, 102.0], 2)

    ranked = assign_ranks([weak, strong, insufficient, mid])
    by_symbol = {r.sector_symbol: r for r in ranked}

    assert by_symbol["XLK"].rs_rank == 1
    assert by_symbol["XLF"].rs_rank == 2
    assert by_symbol["XLE"].rs_rank == 3
    assert by_symbol["SMH"].rs_rank is None  # insufficient is not ranked
    # input order preserved
    assert [r.sector_symbol for r in ranked] == ["XLE", "XLK", "SMH", "XLF"]
