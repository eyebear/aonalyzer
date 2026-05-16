from __future__ import annotations


def calculate_iv_percentile(
    current_iv: float | None,
    historical_ivs: list[float],
    minimum_history_days: int = 30,
) -> float | None:
    """Return IV percentile in [0, 100], or ``None`` when history is insufficient.

    Formula: (count of historical values strictly less than current_iv) /
    total * 100. If current_iv is None or fewer than
    ``minimum_history_days`` historical points are supplied, returns None.
    """
    if current_iv is None:
        return None

    cleaned = [
        float(value)
        for value in (historical_ivs or [])
        if value is not None and value > 0
    ]

    if len(cleaned) < minimum_history_days:
        return None

    below_count = sum(1 for value in cleaned if value < current_iv)
    return below_count / len(cleaned) * 100.0
