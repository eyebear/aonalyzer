from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SwingPoint:
    index: int
    value: float

    def to_dict(self) -> dict[str, float | int]:
        return {"index": self.index, "value": self.value}


def find_swing_lows(
    lows: list[float],
    window: int = 2,
) -> list[SwingPoint]:
    """Find local minima where ``lows[i]`` is strictly less than both
    ``window`` candles before and after.

    Pure deterministic function. ``window`` controls sensitivity:
    smaller picks more swings, larger picks fewer and more significant ones.
    Returns swings in chronological order (oldest first).
    """
    if window < 1:
        return []

    length = len(lows)
    if length < 2 * window + 1:
        return []

    swings: list[SwingPoint] = []
    for index in range(window, length - window):
        value = lows[index]
        if value is None:
            continue

        is_swing = True
        for offset in range(1, window + 1):
            left = lows[index - offset]
            right = lows[index + offset]
            if left is None or right is None:
                is_swing = False
                break
            if not (value < left and value < right):
                is_swing = False
                break

        if is_swing:
            swings.append(SwingPoint(index=index, value=value))

    return swings


def find_swing_highs(
    highs: list[float],
    window: int = 2,
) -> list[SwingPoint]:
    """Find local maxima where ``highs[i]`` is strictly greater than both
    ``window`` candles before and after.
    """
    if window < 1:
        return []

    length = len(highs)
    if length < 2 * window + 1:
        return []

    swings: list[SwingPoint] = []
    for index in range(window, length - window):
        value = highs[index]
        if value is None:
            continue

        is_swing = True
        for offset in range(1, window + 1):
            left = highs[index - offset]
            right = highs[index + offset]
            if left is None or right is None:
                is_swing = False
                break
            if not (value > left and value > right):
                is_swing = False
                break

        if is_swing:
            swings.append(SwingPoint(index=index, value=value))

    return swings


def latest_swing_low_below(
    lows: list[float],
    reference_price: float,
    window: int = 2,
) -> SwingPoint | None:
    """Most recent swing low strictly below ``reference_price``."""
    swings = find_swing_lows(lows, window=window)
    for point in reversed(swings):
        if point.value < reference_price:
            return point
    return None


def latest_swing_high_above(
    highs: list[float],
    reference_price: float,
    window: int = 2,
) -> SwingPoint | None:
    """Most recent swing high strictly above ``reference_price``."""
    swings = find_swing_highs(highs, window=window)
    for point in reversed(swings):
        if point.value > reference_price:
            return point
    return None


__all__ = [
    "SwingPoint",
    "find_swing_highs",
    "find_swing_lows",
    "latest_swing_high_above",
    "latest_swing_low_below",
]
