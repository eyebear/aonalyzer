from app.quant.swing_detector import (
    find_swing_highs,
    find_swing_lows,
    latest_swing_high_above,
    latest_swing_low_below,
)


def test_find_swing_lows_with_clear_v_pattern() -> None:
    # V-shape: index 3 is the strict minimum
    lows = [10.0, 9.0, 8.0, 7.0, 8.0, 9.0, 10.0]
    swings = find_swing_lows(lows, window=2)
    assert len(swings) == 1
    assert swings[0].index == 3
    assert swings[0].value == 7.0


def test_find_swing_lows_returns_empty_for_monotonic() -> None:
    swings = find_swing_lows([10.0, 9.0, 8.0, 7.0, 6.0], window=2)
    assert swings == []


def test_find_swing_lows_returns_empty_when_too_few_rows() -> None:
    assert find_swing_lows([1.0, 2.0, 1.0], window=2) == []


def test_find_swing_lows_returns_multiple_swings_in_chronological_order() -> None:
    lows = [10.0, 8.0, 9.0, 7.0, 8.5, 10.0, 6.0, 9.0, 10.5]
    # need window=1 with both sides strictly greater
    swings = find_swing_lows(lows, window=1)
    indices = [s.index for s in swings]
    # Index 1 (8.0 < 10 and 9): swing low. Index 3 (7.0 < 9 and 8.5): swing low.
    # Index 6 (6.0 < 10 and 9): swing low.
    assert 1 in indices and 3 in indices and 6 in indices


def test_find_swing_lows_with_window_3_requires_six_neighbors() -> None:
    lows = [10.0, 9.0, 8.0, 7.0, 6.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    # Symmetric V, index 5 should be the unique window=3 swing low.
    swings = find_swing_lows(lows, window=3)
    assert [s.index for s in swings] == [5]


def test_find_swing_highs_with_clear_inverted_v() -> None:
    highs = [1.0, 2.0, 3.0, 4.0, 3.0, 2.0, 1.0]
    swings = find_swing_highs(highs, window=2)
    assert len(swings) == 1
    assert swings[0].index == 3
    assert swings[0].value == 4.0


def test_find_swing_highs_returns_empty_for_monotonic() -> None:
    assert find_swing_highs([1.0, 2.0, 3.0, 4.0, 5.0], window=2) == []


def test_latest_swing_low_below_picks_most_recent_lower_than_reference() -> None:
    lows = [10.0, 8.0, 9.0, 7.0, 8.5, 10.0, 6.0, 9.0, 10.5]
    point = latest_swing_low_below(lows=lows, reference_price=9.5, window=1)
    assert point is not None
    assert point.index == 6
    assert point.value == 6.0


def test_latest_swing_low_below_returns_none_when_no_swings_below_reference() -> None:
    lows = [10.0, 8.0, 9.0, 7.0, 8.5]
    point = latest_swing_low_below(lows=lows, reference_price=5.0, window=1)
    assert point is None


def test_latest_swing_high_above_picks_most_recent_higher_than_reference() -> None:
    highs = [1.0, 5.0, 3.0, 7.0, 4.0, 6.0]
    point = latest_swing_high_above(highs=highs, reference_price=4.5, window=1)
    assert point is not None
    # window=1 swing highs: idx 1 (5>1,3), idx 3 (7>3,4), idx 5 needs right neighbor — no
    # Most recent above 4.5: idx 3 with value 7.
    assert point.index == 3
    assert point.value == 7.0


def test_swing_lows_ignore_none_neighbors() -> None:
    lows = [10.0, None, 8.0, 7.0, 8.0, 9.0, 10.0]
    swings = find_swing_lows(lows, window=2)
    # Window=2 at index 3 needs neighbors at 1,2,4,5 all not-None and >7.0.
    # index 1 is None → not a swing.
    assert swings == []


def test_invalid_window_returns_empty() -> None:
    assert find_swing_lows([1.0, 2.0, 1.0], window=0) == []
    assert find_swing_highs([1.0, 2.0, 1.0], window=0) == []
