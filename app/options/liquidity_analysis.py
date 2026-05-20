"""Liquidity scoring for manually pasted option contracts (Phase 15, step 15.7).

Combines spread, open interest, and volume into a 0-100 liquidity score. Only
the components that were actually parsed contribute; with no liquidity fields at
all the score is ``None`` (unknown), never a fabricated number.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class LiquidityResult:
    score: int | None
    components: dict[str, int] = field(default_factory=dict)
    available_fields: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "components": dict(self.components),
            "available_fields": list(self.available_fields),
        }


def score_liquidity(
    spread_percent: float | None,
    open_interest: int | None,
    volume: int | None,
    *,
    max_spread_percent: float = 10.0,
    healthy_open_interest: int = 1000,
    healthy_volume: int = 500,
) -> LiquidityResult:
    """Weighted liquidity score (tighter spread / higher OI / higher volume = better).

    Each present component contributes up to its max weight; the final score is
    rescaled to 0-100 over the components that were available so a contract with
    only OI parsed is still scored on what is known.
    """
    weights = {"spread": 40, "open_interest": 35, "volume": 25}
    earned: dict[str, int] = {}
    available_total = 0

    if spread_percent is not None and max_spread_percent > 0:
        ratio = max(0.0, 1.0 - (spread_percent / max_spread_percent))
        earned["spread"] = round(ratio * weights["spread"])
        available_total += weights["spread"]

    if open_interest is not None and healthy_open_interest > 0:
        ratio = min(1.0, open_interest / healthy_open_interest)
        earned["open_interest"] = round(ratio * weights["open_interest"])
        available_total += weights["open_interest"]

    if volume is not None and healthy_volume > 0:
        ratio = min(1.0, volume / healthy_volume)
        earned["volume"] = round(ratio * weights["volume"])
        available_total += weights["volume"]

    if available_total == 0:
        return LiquidityResult(score=None, components={}, available_fields=[])

    raw = sum(earned.values())
    score = round(raw / available_total * 100)
    score = max(0, min(100, score))

    return LiquidityResult(
        score=score,
        components=earned,
        available_fields=list(earned.keys()),
    )


__all__ = ["LiquidityResult", "score_liquidity"]
