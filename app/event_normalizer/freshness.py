from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


DEFAULT_FRESH_WINDOW_HOURS = 24
DEFAULT_STALE_WINDOW_DAYS = 7


@dataclass(frozen=True)
class EventFreshnessVerdict:
    is_fresh: bool
    is_stale: bool
    age_minutes: int | None
    reason: str

    def to_dict(self) -> dict[str, object]:
        return {
            "is_fresh": self.is_fresh,
            "is_stale": self.is_stale,
            "age_minutes": self.age_minutes,
            "reason": self.reason,
        }


class EventFreshnessChecker:
    def __init__(
        self,
        fresh_window_hours: int = DEFAULT_FRESH_WINDOW_HOURS,
        stale_window_days: int = DEFAULT_STALE_WINDOW_DAYS,
    ) -> None:
        self.fresh_window_hours = fresh_window_hours
        self.stale_window_days = stale_window_days

    def check(
        self,
        event_time: datetime | None,
        now: datetime | None = None,
    ) -> EventFreshnessVerdict:
        current_time = now or datetime.now(timezone.utc)

        if event_time is None:
            return EventFreshnessVerdict(
                is_fresh=False,
                is_stale=False,
                age_minutes=None,
                reason="event_time is missing",
            )

        normalized = (
            event_time
            if event_time.tzinfo is not None
            else event_time.replace(tzinfo=timezone.utc)
        )

        age = current_time - normalized
        age_minutes = int(age.total_seconds() // 60)

        if age >= timedelta(days=self.stale_window_days):
            return EventFreshnessVerdict(
                is_fresh=False,
                is_stale=True,
                age_minutes=age_minutes,
                reason=(
                    f"event is older than {self.stale_window_days}d "
                    f"(age={age_minutes}m)"
                ),
            )

        if age <= timedelta(hours=self.fresh_window_hours):
            return EventFreshnessVerdict(
                is_fresh=True,
                is_stale=False,
                age_minutes=age_minutes,
                reason=(
                    f"event is within last {self.fresh_window_hours}h "
                    f"(age={age_minutes}m)"
                ),
            )

        return EventFreshnessVerdict(
            is_fresh=False,
            is_stale=False,
            age_minutes=age_minutes,
            reason=(
                f"event is older than {self.fresh_window_hours}h "
                f"and younger than {self.stale_window_days}d (age={age_minutes}m)"
            ),
        )
