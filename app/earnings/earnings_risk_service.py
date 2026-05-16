from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.database.base import Base
from app.earnings.days_to_earnings_calculator import (
    DaysToEarningsResult,
    calculate_days_to_earnings,
)
from app.earnings.earnings_before_expiration_checker import (
    EARNINGS_BEFORE_EXPIRATION_NOT_APPLICABLE,
    EARNINGS_BEFORE_EXPIRATION_TRUE,
    EarningsBeforeExpirationResult,
    check_earnings_before_expiration,
)
from app.earnings.earnings_models import EarningsRiskSnapshot
from app.profiles.profile_manager import profile_manager


RISK_LABEL_EARNINGS_BEFORE_EXPIRATION = "EARNINGS_BEFORE_EXPIRATION"
RISK_LABEL_EARNINGS_INSIDE_WINDOW = "EARNINGS_INSIDE_WINDOW"
RISK_LABEL_NO_EARNINGS_NEAR = "NO_EARNINGS_NEAR"
RISK_LABEL_EARNINGS_DATA_NOT_AVAILABLE = "EARNINGS_DATA_NOT_AVAILABLE"


@dataclass(frozen=True)
class EarningsRiskComputation:
    symbol: str
    snapshot_date: date
    next_earnings_datetime_utc: datetime | None
    days_to_earnings: int | None
    earnings_within_window: bool
    earnings_risk_window_days: int
    earnings_before_expiration: str
    manual_option_expiration_date: date | None
    risk_label: str
    risk_reason: str
    data_sufficiency_status: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "snapshot_date": self.snapshot_date.isoformat(),
            "next_earnings_datetime_utc": (
                self.next_earnings_datetime_utc.isoformat()
                if self.next_earnings_datetime_utc is not None
                else None
            ),
            "days_to_earnings": self.days_to_earnings,
            "earnings_within_window": self.earnings_within_window,
            "earnings_risk_window_days": self.earnings_risk_window_days,
            "earnings_before_expiration": self.earnings_before_expiration,
            "manual_option_expiration_date": (
                self.manual_option_expiration_date.isoformat()
                if self.manual_option_expiration_date is not None
                else None
            ),
            "risk_label": self.risk_label,
            "risk_reason": self.risk_reason,
            "data_sufficiency_status": self.data_sufficiency_status,
        }


@dataclass
class EarningsRiskRefreshResult:
    requested_symbols: list[str] = field(default_factory=list)
    successful_symbols: list[str] = field(default_factory=list)
    no_data_symbols: list[str] = field(default_factory=list)
    failed_symbols: list[str] = field(default_factory=list)

    snapshots_inserted: int = 0
    snapshots_updated: int = 0
    per_symbol_results: list[dict[str, Any]] = field(default_factory=list)
    failed_reasons: dict[str, str] = field(default_factory=dict)

    @property
    def records_created(self) -> int:
        return self.snapshots_inserted

    @property
    def records_updated(self) -> int:
        return self.snapshots_updated

    @property
    def records_failed(self) -> int:
        return len(self.failed_symbols)

    def to_dict(self) -> dict[str, Any]:
        return {
            "requested_symbols": self.requested_symbols,
            "successful_symbols": self.successful_symbols,
            "no_data_symbols": self.no_data_symbols,
            "failed_symbols": self.failed_symbols,
            "snapshots_inserted": self.snapshots_inserted,
            "snapshots_updated": self.snapshots_updated,
            "records_created": self.records_created,
            "records_updated": self.records_updated,
            "records_failed": self.records_failed,
            "per_symbol_results": self.per_symbol_results,
            "failed_reasons": self.failed_reasons,
        }


class EarningsRiskService:
    """Assembles an ``EarningsRiskSnapshot`` per (symbol, snapshot_date).

    Phase 10 independence guarantee: this service does NOT require any
    manual-option snapshot or option-chain row to function. If no option
    data exists, ``earnings_before_expiration`` is ``NOT_APPLICABLE`` and
    the rest of the snapshot is unaffected.
    """

    def __init__(
        self,
        earnings_risk_window_days: int | None = None,
    ) -> None:
        self._override_window_days = earnings_risk_window_days

    def ensure_tables(self, db: Session) -> None:
        Base.metadata.create_all(bind=db.get_bind())

    def compute_for_symbol(
        self,
        db: Session,
        symbol: str,
        now: datetime | None = None,
    ) -> EarningsRiskComputation:
        current_time = now or datetime.now(timezone.utc)
        snapshot_date = current_time.date()

        window_days = (
            self._override_window_days
            if self._override_window_days is not None
            else profile_manager.get_active_profile().earnings_risk_window_days
        )

        days_result: DaysToEarningsResult = calculate_days_to_earnings(
            db=db,
            symbol=symbol,
            now=current_time,
        )

        before_expiration_result: EarningsBeforeExpirationResult = (
            check_earnings_before_expiration(
                db=db,
                symbol=symbol,
                next_earnings_datetime_utc=days_result.next_earnings_datetime_utc,
            )
        )

        if not days_result.found_future_earnings:
            return EarningsRiskComputation(
                symbol=symbol.upper(),
                snapshot_date=snapshot_date,
                next_earnings_datetime_utc=None,
                days_to_earnings=None,
                earnings_within_window=False,
                earnings_risk_window_days=window_days,
                earnings_before_expiration=EARNINGS_BEFORE_EXPIRATION_NOT_APPLICABLE,
                manual_option_expiration_date=None,
                risk_label=RISK_LABEL_EARNINGS_DATA_NOT_AVAILABLE,
                risk_reason=(
                    "No future earnings event is on file for this symbol; "
                    "stock-level research continues without an earnings "
                    "constraint."
                ),
                data_sufficiency_status="EARNINGS_DATA_NOT_AVAILABLE",
            )

        within_window = (
            days_result.days_to_earnings is not None
            and days_result.days_to_earnings <= window_days
        )

        if (
            before_expiration_result.status == EARNINGS_BEFORE_EXPIRATION_TRUE
            and within_window
        ):
            risk_label = RISK_LABEL_EARNINGS_BEFORE_EXPIRATION
            risk_reason = (
                f"Earnings in {days_result.days_to_earnings} day(s) and falls "
                f"before manual option expiration "
                f"({before_expiration_result.option_expiration_date})."
            )
        elif before_expiration_result.status == EARNINGS_BEFORE_EXPIRATION_TRUE:
            risk_label = RISK_LABEL_EARNINGS_BEFORE_EXPIRATION
            risk_reason = (
                f"Earnings in {days_result.days_to_earnings} day(s) falls "
                f"before manual option expiration "
                f"({before_expiration_result.option_expiration_date})."
            )
        elif within_window:
            risk_label = RISK_LABEL_EARNINGS_INSIDE_WINDOW
            risk_reason = (
                f"Earnings in {days_result.days_to_earnings} day(s) is within "
                f"the {window_days}-day risk window."
            )
        else:
            risk_label = RISK_LABEL_NO_EARNINGS_NEAR
            risk_reason = (
                f"Earnings in {days_result.days_to_earnings} day(s) is outside "
                f"the {window_days}-day risk window."
            )

        return EarningsRiskComputation(
            symbol=symbol.upper(),
            snapshot_date=snapshot_date,
            next_earnings_datetime_utc=days_result.next_earnings_datetime_utc,
            days_to_earnings=days_result.days_to_earnings,
            earnings_within_window=within_window,
            earnings_risk_window_days=window_days,
            earnings_before_expiration=before_expiration_result.status,
            manual_option_expiration_date=before_expiration_result.option_expiration_date,
            risk_label=risk_label,
            risk_reason=risk_reason,
            data_sufficiency_status="SUFFICIENT",
        )

    def persist_snapshot(
        self,
        db: Session,
        computation: EarningsRiskComputation,
    ) -> tuple[EarningsRiskSnapshot, bool]:
        self.ensure_tables(db)

        existing = (
            db.query(EarningsRiskSnapshot)
            .filter(EarningsRiskSnapshot.symbol == computation.symbol)
            .filter(EarningsRiskSnapshot.snapshot_date == computation.snapshot_date)
            .one_or_none()
        )

        values = {
            "next_earnings_datetime_utc": computation.next_earnings_datetime_utc,
            "days_to_earnings": computation.days_to_earnings,
            "earnings_within_window": computation.earnings_within_window,
            "earnings_risk_window_days": computation.earnings_risk_window_days,
            "earnings_before_expiration": computation.earnings_before_expiration,
            "manual_option_expiration_date": computation.manual_option_expiration_date,
            "risk_label": computation.risk_label,
            "risk_reason": computation.risk_reason,
            "data_sufficiency_status": computation.data_sufficiency_status,
        }

        if existing is None:
            row = EarningsRiskSnapshot(
                symbol=computation.symbol,
                snapshot_date=computation.snapshot_date,
                **values,
            )
            db.add(row)
            db.flush()
            return row, True

        for key, value in values.items():
            setattr(existing, key, value)
        db.flush()
        return existing, False

    def refresh_earnings_risk(
        self,
        db: Session,
        symbols: list[str] | None = None,
        now: datetime | None = None,
    ) -> EarningsRiskRefreshResult:
        self.ensure_tables(db)

        normalized = self._normalize_symbols(symbols or [])
        result = EarningsRiskRefreshResult(requested_symbols=normalized)

        if not normalized:
            db.commit()
            return result

        for symbol in normalized:
            try:
                computation = self.compute_for_symbol(db=db, symbol=symbol, now=now)
            except Exception as exc:
                result.failed_symbols.append(symbol)
                result.failed_reasons[symbol] = str(exc)
                continue

            result.per_symbol_results.append(computation.to_dict())

            try:
                _, inserted = self.persist_snapshot(db=db, computation=computation)
            except Exception as exc:
                db.rollback()
                result.failed_symbols.append(symbol)
                result.failed_reasons[symbol] = str(exc)
                continue

            if computation.risk_label == RISK_LABEL_EARNINGS_DATA_NOT_AVAILABLE:
                result.no_data_symbols.append(symbol)
            else:
                result.successful_symbols.append(symbol)

            if inserted:
                result.snapshots_inserted += 1
            else:
                result.snapshots_updated += 1

        db.commit()
        return result

    def _normalize_symbols(self, symbols: list[str]) -> list[str]:
        normalized: list[str] = []
        for s in symbols:
            clean = s.strip().upper()
            if clean and clean not in normalized:
                normalized.append(clean)
        return normalized


__all__ = [
    "EarningsRiskComputation",
    "EarningsRiskRefreshResult",
    "EarningsRiskService",
    "RISK_LABEL_EARNINGS_BEFORE_EXPIRATION",
    "RISK_LABEL_EARNINGS_DATA_NOT_AVAILABLE",
    "RISK_LABEL_EARNINGS_INSIDE_WINDOW",
    "RISK_LABEL_NO_EARNINGS_NEAR",
]
