"""Pure, deterministic sector relative-strength logic (Phase 13, steps 13.7-13.9).

Relative strength = sector return minus benchmark return over a fixed lookback.
Sectors are ranked within a benchmark group (1 = strongest). All functions are
side-effect free; insufficient price history yields a clean ``INSUFFICIENT``
state rather than an invented number.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

# Sector-vs-benchmark labels.
SECTOR_OUTPERFORM = "OUTPERFORM"
SECTOR_UNDERPERFORM = "UNDERPERFORM"
SECTOR_INLINE = "INLINE"
SECTOR_INSUFFICIENT = "INSUFFICIENT"

SUFFICIENT = "SUFFICIENT"
INSUFFICIENT_PRICE_HISTORY = "INSUFFICIENT_PRICE_HISTORY"


@dataclass(frozen=True)
class SectorStrengthResult:
    sector_symbol: str
    benchmark_symbol: str
    lookback_days: int
    sector_return_pct: float | None
    benchmark_return_pct: float | None
    relative_strength: float | None
    trend: str
    rs_rank: int | None
    sector_row_count: int
    data_sufficiency_status: str
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "sector_symbol": self.sector_symbol,
            "benchmark_symbol": self.benchmark_symbol,
            "lookback_days": self.lookback_days,
            "sector_return_pct": self.sector_return_pct,
            "benchmark_return_pct": self.benchmark_return_pct,
            "relative_strength": self.relative_strength,
            "trend": self.trend,
            "rs_rank": self.rs_rank,
            "sector_row_count": self.sector_row_count,
            "data_sufficiency_status": self.data_sufficiency_status,
            "reason": self.reason,
        }


def compute_period_return(closes: list[float], lookback_days: int) -> float | None:
    """Return fractional change over ``lookback_days`` (e.g. 0.05 = +5%).

    Needs ``lookback_days + 1`` closes; returns None otherwise or when the
    reference close is zero.
    """
    if lookback_days < 1 or len(closes) < lookback_days + 1:
        return None
    past = closes[-(lookback_days + 1)]
    current = closes[-1]
    if not past:
        return None
    return (current - past) / abs(past)


def compute_relative_strength(
    sector_symbol: str,
    benchmark_symbol: str,
    sector_closes: list[float],
    benchmark_closes: list[float],
    lookback_days: int = 20,
    inline_band: float = 0.005,
) -> SectorStrengthResult:
    """Relative strength of one sector ETF vs one benchmark over the lookback."""
    sector_return = compute_period_return(sector_closes, lookback_days)
    benchmark_return = compute_period_return(benchmark_closes, lookback_days)

    if sector_return is None or benchmark_return is None:
        missing = []
        if sector_return is None:
            missing.append(f"{sector_symbol} (sector)")
        if benchmark_return is None:
            missing.append(f"{benchmark_symbol} (benchmark)")
        return SectorStrengthResult(
            sector_symbol=sector_symbol,
            benchmark_symbol=benchmark_symbol,
            lookback_days=lookback_days,
            sector_return_pct=sector_return,
            benchmark_return_pct=benchmark_return,
            relative_strength=None,
            trend=SECTOR_INSUFFICIENT,
            rs_rank=None,
            sector_row_count=len(sector_closes),
            data_sufficiency_status=INSUFFICIENT_PRICE_HISTORY,
            reason=(
                "Insufficient price history to compute "
                f"{lookback_days}-day return for: {', '.join(missing)}."
            ),
        )

    relative_strength = sector_return - benchmark_return

    if relative_strength > inline_band:
        trend = SECTOR_OUTPERFORM
    elif relative_strength < -inline_band:
        trend = SECTOR_UNDERPERFORM
    else:
        trend = SECTOR_INLINE

    return SectorStrengthResult(
        sector_symbol=sector_symbol,
        benchmark_symbol=benchmark_symbol,
        lookback_days=lookback_days,
        sector_return_pct=sector_return,
        benchmark_return_pct=benchmark_return,
        relative_strength=relative_strength,
        trend=trend,
        rs_rank=None,
        sector_row_count=len(sector_closes),
        data_sufficiency_status=SUFFICIENT,
    )


def assign_ranks(results: list[SectorStrengthResult]) -> list[SectorStrengthResult]:
    """Return a new list with ``rs_rank`` set within the group (1 = strongest).

    Only results with a computable ``relative_strength`` are ranked; insufficient
    rows keep ``rs_rank=None``. Ties are broken deterministically by sector symbol
    so ranking is stable and testable. Input order is preserved in the output.
    """
    rankable = [r for r in results if r.relative_strength is not None]
    ordered = sorted(
        rankable,
        key=lambda r: (-r.relative_strength, r.sector_symbol),  # type: ignore[operator]
    )
    rank_by_symbol = {
        (r.sector_symbol, r.benchmark_symbol): index + 1
        for index, r in enumerate(ordered)
    }

    ranked: list[SectorStrengthResult] = []
    for r in results:
        key = (r.sector_symbol, r.benchmark_symbol)
        if key in rank_by_symbol:
            ranked.append(replace(r, rs_rank=rank_by_symbol[key]))
        else:
            ranked.append(r)
    return ranked


__all__ = [
    "INSUFFICIENT_PRICE_HISTORY",
    "SECTOR_INLINE",
    "SECTOR_INSUFFICIENT",
    "SECTOR_OUTPERFORM",
    "SECTOR_UNDERPERFORM",
    "SUFFICIENT",
    "SectorStrengthResult",
    "assign_ranks",
    "compute_period_return",
    "compute_relative_strength",
]
