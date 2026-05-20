from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

# Tri-state encoded explicitly so callers don't conflate "no info" with
# "no option supplied." NOT_APPLICABLE is the safe default when stock-only
# research is happening.
EARNINGS_BEFORE_EXPIRATION_TRUE = "TRUE"
EARNINGS_BEFORE_EXPIRATION_FALSE = "FALSE"
EARNINGS_BEFORE_EXPIRATION_NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass(frozen=True)
class EarningsBeforeExpirationResult:
    status: str
    earnings_datetime_utc: datetime | None
    option_expiration_date: date | None
    reason: str

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "earnings_datetime_utc": self.earnings_datetime_utc.isoformat()
            if self.earnings_datetime_utc is not None
            else None,
            "option_expiration_date": self.option_expiration_date.isoformat()
            if self.option_expiration_date is not None
            else None,
            "reason": self.reason,
        }


def check_earnings_before_expiration(
    db: Session,
    symbol: str,
    next_earnings_datetime_utc: datetime | None,
) -> EarningsBeforeExpirationResult:
    """Returns whether the earliest future earnings falls **before** the
    expiration of the most-recent manual option snapshot for ``symbol``.

    Tri-state:
    - TRUE: an option expiration exists AND earnings is before it (capital-risk situation)
    - FALSE: an option expiration exists AND earnings is on/after it (safer)
    - NOT_APPLICABLE: no manual option snapshot OR no parsed expiration date

    Phase 10's independence guarantee: stock-only research must never require
    a manual option snapshot. ``NOT_APPLICABLE`` is the correct answer when
    one isn't supplied — never a failure, never a forced default.
    """
    if next_earnings_datetime_utc is None:
        return EarningsBeforeExpirationResult(
            status=EARNINGS_BEFORE_EXPIRATION_NOT_APPLICABLE,
            earnings_datetime_utc=None,
            option_expiration_date=None,
            reason="No future earnings event is known.",
        )

    expiration = _read_latest_manual_option_expiration(db=db, symbol=symbol)

    if expiration is None:
        return EarningsBeforeExpirationResult(
            status=EARNINGS_BEFORE_EXPIRATION_NOT_APPLICABLE,
            earnings_datetime_utc=next_earnings_datetime_utc,
            option_expiration_date=None,
            reason=(
                "No manual option snapshot with a parsed expiration date "
                "is on file for this symbol."
            ),
        )

    normalized_earnings = (
        next_earnings_datetime_utc
        if next_earnings_datetime_utc.tzinfo is not None
        else next_earnings_datetime_utc.replace(tzinfo=timezone.utc)
    )

    earnings_day = normalized_earnings.date()

    if earnings_day < expiration:
        return EarningsBeforeExpirationResult(
            status=EARNINGS_BEFORE_EXPIRATION_TRUE,
            earnings_datetime_utc=normalized_earnings,
            option_expiration_date=expiration,
            reason=(
                f"Earnings on {earnings_day} occurs before the manual option "
                f"expiration on {expiration}."
            ),
        )

    return EarningsBeforeExpirationResult(
        status=EARNINGS_BEFORE_EXPIRATION_FALSE,
        earnings_datetime_utc=normalized_earnings,
        option_expiration_date=expiration,
        reason=(
            f"Earnings on {earnings_day} occurs on or after the manual option "
            f"expiration on {expiration}."
        ),
    )


def _read_latest_manual_option_expiration(
    db: Session,
    symbol: str,
) -> date | None:
    """Look up the most recently created manual option snapshot for the
    symbol that has a non-null expiration date.

    Reads ``manual_option_snapshots`` directly via raw SQL because that
    table is owned by ``ManualOptionInputService.ensure_manual_option_tables``
    (created lazily on first paste, not via ``Base.metadata.create_all``).
    If the table doesn't exist yet, we treat it as "no option data" and
    return None — never raise.
    """
    inspector = inspect(db.get_bind())
    if "manual_option_snapshots" not in inspector.get_table_names():
        return None

    row = (
        db.execute(
            text(
                """
                SELECT expiration_date
                FROM manual_option_snapshots
                WHERE UPPER(symbol) = :symbol
                  AND expiration_date IS NOT NULL
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """
            ),
            {"symbol": symbol.upper()},
        )
        .mappings()
        .first()
    )

    if row is None:
        return None

    raw_value = row.get("expiration_date")
    if raw_value is None:
        return None

    if isinstance(raw_value, date) and not isinstance(raw_value, datetime):
        return raw_value

    if isinstance(raw_value, datetime):
        return raw_value.date()

    text_value = str(raw_value)
    try:
        return datetime.fromisoformat(text_value).date()
    except ValueError:
        pass

    try:
        return datetime.strptime(text_value[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


__all__ = [
    "EARNINGS_BEFORE_EXPIRATION_FALSE",
    "EARNINGS_BEFORE_EXPIRATION_NOT_APPLICABLE",
    "EARNINGS_BEFORE_EXPIRATION_TRUE",
    "EarningsBeforeExpirationResult",
    "check_earnings_before_expiration",
]
