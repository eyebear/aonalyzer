from __future__ import annotations


def calculate_iv_rank(
    current_iv: float | None,
    historical_ivs: list[float],
    minimum_history_days: int = 30,
) -> float | None:
    """Return IV rank in [0, 100], or ``None`` when history is insufficient.

    Formula: (current - min) / (max - min) * 100. If current_iv is None or
    fewer than ``minimum_history_days`` historical points are supplied,
    returns None. If max == min, returns 50.0 (mid-rank) — the value is at
    its only-known level.
    """
    if current_iv is None:
        return None

    if not historical_ivs or len(historical_ivs) < minimum_history_days:
        return None

    cleaned = [
        float(value)
        for value in historical_ivs
        if value is not None and value > 0
    ]
    if len(cleaned) < minimum_history_days:
        return None

    high = max(cleaned)
    low = min(cleaned)

    if high == low:
        return 50.0

    rank = (current_iv - low) / (high - low) * 100.0
    if rank < 0:
        return 0.0
    if rank > 100:
        return 100.0
    return rank
