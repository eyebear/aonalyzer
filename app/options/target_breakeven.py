"""Target-vs-breakeven logic (Phase 15, step 15.10).

Checks whether the stock's target price clears the option breakeven with enough
margin, and whether the breakeven sits within a reasonable distance of the
current underlying. Each check is skipped when its inputs are absent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.options.breakeven import breakeven_distance_percent, is_put
from app.options.option_filters import FAIL, PASS, SKIPPED, WARN, FilterOutcome

BREAKEVEN_TOO_FAR = "BREAKEVEN_TOO_FAR"
TARGET_BELOW_BREAKEVEN = "TARGET_BELOW_BREAKEVEN"
TARGET_MARGIN_TOO_THIN = "TARGET_MARGIN_TOO_THIN"


@dataclass(frozen=True)
class TargetBreakevenResult:
    outcomes: list[FilterOutcome] = field(default_factory=list)
    breakeven_distance_percent: float | None = None
    target_margin_percent: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcomes": [o.to_dict() for o in self.outcomes],
            "breakeven_distance_percent": self.breakeven_distance_percent,
            "target_margin_percent": self.target_margin_percent,
        }


def evaluate_target_vs_breakeven(
    option_type: str | None,
    breakeven: float | None,
    target_price: float | None,
    underlying_price: float | None,
    *,
    minimum_target_breakeven_margin_percent: float,
    max_breakeven_distance_percent: float,
    reject_if_target_below_breakeven: bool,
) -> TargetBreakevenResult:
    outcomes: list[FilterOutcome] = []

    distance = breakeven_distance_percent(option_type, breakeven, underlying_price)
    if distance is None:
        outcomes.append(
            FilterOutcome(
                "breakeven_distance",
                SKIPPED,
                detail="Need breakeven and underlying price to measure distance.",
            )
        )
    elif distance > max_breakeven_distance_percent:
        outcomes.append(
            FilterOutcome(
                "breakeven_distance",
                FAIL,
                label=BREAKEVEN_TOO_FAR,
                detail=(
                    f"Breakeven is {distance:.2f}% from spot, beyond the maximum "
                    f"{max_breakeven_distance_percent:.2f}%."
                ),
                value=distance,
            )
        )
    else:
        outcomes.append(
            FilterOutcome(
                "breakeven_distance",
                PASS,
                detail=f"Breakeven {distance:.2f}% from spot.",
                value=distance,
            )
        )

    margin: float | None = None
    if breakeven is None or target_price is None or breakeven <= 0:
        outcomes.append(
            FilterOutcome(
                "target_margin",
                SKIPPED,
                detail="Need breakeven and a stock target to compare.",
            )
        )
    else:
        if is_put(option_type):
            on_profitable_side = target_price < breakeven
            margin = (breakeven - target_price) / breakeven * 100.0
        else:
            on_profitable_side = target_price > breakeven
            margin = (target_price - breakeven) / breakeven * 100.0

        if not on_profitable_side:
            status = FAIL if reject_if_target_below_breakeven else WARN
            outcomes.append(
                FilterOutcome(
                    "target_margin",
                    status,
                    label=TARGET_BELOW_BREAKEVEN,
                    detail="Stock target is on the unprofitable side of breakeven.",
                    value=margin,
                )
            )
        elif margin < minimum_target_breakeven_margin_percent:
            outcomes.append(
                FilterOutcome(
                    "target_margin",
                    FAIL,
                    label=TARGET_MARGIN_TOO_THIN,
                    detail=(
                        f"Target clears breakeven by only {margin:.2f}%, below the "
                        f"minimum {minimum_target_breakeven_margin_percent:.2f}%."
                    ),
                    value=margin,
                )
            )
        else:
            outcomes.append(
                FilterOutcome(
                    "target_margin",
                    PASS,
                    detail=f"Target clears breakeven by {margin:.2f}%.",
                    value=margin,
                )
            )

    return TargetBreakevenResult(
        outcomes=outcomes,
        breakeven_distance_percent=distance,
        target_margin_percent=margin,
    )


__all__ = [
    "BREAKEVEN_TOO_FAR",
    "TARGET_BELOW_BREAKEVEN",
    "TARGET_MARGIN_TOO_THIN",
    "TargetBreakevenResult",
    "evaluate_target_vs_breakeven",
]
