"""Phases 39-40 — deterministic forward-return computation.

Shared helper that computes a symbol's forward stock return and target/stop
hit over a fixed horizon using persisted ``daily_prices``. It NEVER invents
missing future prices: when fewer than ``horizon_days`` trading bars exist
after the signal bar, the result is marked unavailable. Used by signal-outcome
tracking (Phase 39), rejection-outcome tracking (Phase 40), and override-outcome
evaluation (Phase 38).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database.models import DailyPrice

DIRECTION_LONG = "LONG"
DIRECTION_SHORT = "SHORT"


def _to_float(value: Any) -> float | None:
    """Coerce a possibly-Decimal price column to float (DailyPrice uses Numeric)."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@dataclass
class ForwardReturn:
    horizon_days: int
    available: bool
    start_close: float | None = None
    end_close: float | None = None
    return_pct: float | None = None
    target_hit: bool | None = None
    stop_hit: bool | None = None
    bars_used: int = 0
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "horizon_days": self.horizon_days,
            "available": self.available,
            "start_close": self.start_close,
            "end_close": self.end_close,
            "return_pct": self.return_pct,
            "target_hit": self.target_hit,
            "stop_hit": self.stop_hit,
            "bars_used": self.bars_used,
            "reason": self.reason,
        }


def compute_forward_return(
    db: Session,
    symbol: str,
    signal_date: date,
    horizon_days: int,
    *,
    target_price: float | None = None,
    stop_price: float | None = None,
    direction: str = DIRECTION_LONG,
) -> ForwardReturn:
    """Compute the forward return over ``horizon_days`` trading bars.

    The window is the signal bar (first bar at/after ``signal_date``) through
    ``horizon_days`` bars later. Returns ``available=False`` when there is no
    signal bar or fewer than ``horizon_days`` subsequent bars (no fabrication).
    """
    try:
        rows = (
            db.query(DailyPrice)
            .filter(DailyPrice.symbol == symbol.strip().upper())
            .filter(DailyPrice.price_date >= signal_date)
            .order_by(DailyPrice.price_date.asc())
            .all()
        )
    except SQLAlchemyError:
        return ForwardReturn(horizon_days=horizon_days, available=False, reason="DB_ERROR")

    if not rows:
        return ForwardReturn(
            horizon_days=horizon_days,
            available=False,
            reason="NO_PRICE_BARS_AT_OR_AFTER_SIGNAL",
        )

    # Need the signal bar + horizon_days subsequent bars.
    if len(rows) <= horizon_days:
        return ForwardReturn(
            horizon_days=horizon_days,
            available=False,
            start_close=_to_float(rows[0].close_price),
            bars_used=len(rows),
            reason="INSUFFICIENT_FORWARD_PRICE_HISTORY",
        )

    is_long = (direction or DIRECTION_LONG).upper() != DIRECTION_SHORT
    window = rows[: horizon_days + 1]
    start_close = _to_float(window[0].close_price)
    end_close = _to_float(window[horizon_days].close_price)

    if start_close in (None, 0) or end_close is None:
        return ForwardReturn(
            horizon_days=horizon_days,
            available=False,
            reason="INVALID_START_CLOSE",
            bars_used=len(window),
        )

    raw_return = (end_close - start_close) / start_close * 100.0
    return_pct = raw_return if is_long else -raw_return

    target_hit = None
    stop_hit = None
    if target_price is not None or stop_price is not None:
        target_hit = False
        stop_hit = False
        for bar in window:
            high = _to_float(bar.high_price)
            low = _to_float(bar.low_price)
            if target_price is not None and high is not None and low is not None:
                if is_long and high >= target_price:
                    target_hit = True
                if not is_long and low <= target_price:
                    target_hit = True
            if stop_price is not None and high is not None and low is not None:
                if is_long and low <= stop_price:
                    stop_hit = True
                if not is_long and high >= stop_price:
                    stop_hit = True

    return ForwardReturn(
        horizon_days=horizon_days,
        available=True,
        start_close=start_close,
        end_close=end_close,
        return_pct=round(return_pct, 4),
        target_hit=target_hit,
        stop_hit=stop_hit,
        bars_used=len(window),
    )


__all__ = ["DIRECTION_LONG", "DIRECTION_SHORT", "ForwardReturn", "compute_forward_return"]
