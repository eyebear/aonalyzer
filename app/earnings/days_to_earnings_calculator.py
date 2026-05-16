from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from app.earnings.earnings_models import EarningsEvent


@dataclass(frozen=True)
class DaysToEarningsResult:
    next_earnings_datetime_utc: datetime | None
    days_to_earnings: int | None
    found_future_earnings: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "next_earnings_datetime_utc": self.next_earnings_datetime_utc.isoformat()
            if self.next_earnings_datetime_utc is not None
            else None,
            "days_to_earnings": self.days_to_earnings,
            "found_future_earnings": self.found_future_earnings,
        }


def calculate_days_to_earnings(
    db: Session,
    symbol: str,
    now: datetime | None = None,
) -> DaysToEarningsResult:
    """Find the soonest future earnings event for ``symbol``.

    Returns days remaining as a non-negative integer (today = 0). Returns
    ``found_future_earnings=False`` when no future row exists, so callers can
    distinguish "no data" from "earnings is today".
    """
    current_time = now or datetime.now(timezone.utc)

    event: EarningsEvent | None = (
        db.query(EarningsEvent)
        .filter(EarningsEvent.symbol == symbol.upper())
        .filter(EarningsEvent.earnings_datetime_utc >= current_time)
        .order_by(EarningsEvent.earnings_datetime_utc.asc())
        .first()
    )

    if event is None:
        return DaysToEarningsResult(
            next_earnings_datetime_utc=None,
            days_to_earnings=None,
            found_future_earnings=False,
        )

    earnings_datetime = event.earnings_datetime_utc
    if earnings_datetime.tzinfo is None:
        earnings_datetime = earnings_datetime.replace(tzinfo=timezone.utc)

    today = current_time.date()
    earnings_day = earnings_datetime.date()
    days = max((earnings_day - today).days, 0)

    return DaysToEarningsResult(
        next_earnings_datetime_utc=earnings_datetime,
        days_to_earnings=days,
        found_future_earnings=True,
    )
