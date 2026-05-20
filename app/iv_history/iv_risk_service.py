from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.common.service_utils import ensure_tables, normalize_symbols
from app.iv_history.iv_models import IvHistoryDay, IvRiskSnapshot
from app.iv_history.iv_percentile_calculator import calculate_iv_percentile
from app.iv_history.iv_rank_calculator import calculate_iv_rank
from app.profiles.profile_manager import profile_manager

DEFAULT_MINIMUM_IV_HISTORY_DAYS = 30


RISK_LABEL_IV_LOW = "IV_LOW"
RISK_LABEL_IV_WARNING = "IV_WARNING"
RISK_LABEL_IV_REJECT = "IV_REJECT"
RISK_LABEL_IV_DATA_NOT_AVAILABLE = "IV_DATA_NOT_AVAILABLE"
RISK_LABEL_INSUFFICIENT_IV_HISTORY = "INSUFFICIENT_IV_HISTORY"


@dataclass(frozen=True)
class IvRiskComputation:
    symbol: str
    snapshot_date: date

    current_iv: float | None
    iv_rank: float | None
    iv_percentile: float | None
    iv_history_days_used: int | None

    iv_warning_threshold: float | None
    iv_reject_threshold: float | None

    risk_label: str
    risk_reason: str
    data_sufficiency_status: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "snapshot_date": self.snapshot_date.isoformat(),
            "current_iv": self.current_iv,
            "iv_rank": self.iv_rank,
            "iv_percentile": self.iv_percentile,
            "iv_history_days_used": self.iv_history_days_used,
            "iv_warning_threshold": self.iv_warning_threshold,
            "iv_reject_threshold": self.iv_reject_threshold,
            "risk_label": self.risk_label,
            "risk_reason": self.risk_reason,
            "data_sufficiency_status": self.data_sufficiency_status,
        }


@dataclass
class IvRiskRefreshResult:
    requested_symbols: list[str] = field(default_factory=list)
    successful_symbols: list[str] = field(default_factory=list)
    no_data_symbols: list[str] = field(default_factory=list)
    insufficient_symbols: list[str] = field(default_factory=list)
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
            "insufficient_symbols": self.insufficient_symbols,
            "failed_symbols": self.failed_symbols,
            "snapshots_inserted": self.snapshots_inserted,
            "snapshots_updated": self.snapshots_updated,
            "records_created": self.records_created,
            "records_updated": self.records_updated,
            "records_failed": self.records_failed,
            "per_symbol_results": self.per_symbol_results,
            "failed_reasons": self.failed_reasons,
        }


class IvRiskService:
    def __init__(
        self,
        minimum_history_days: int = DEFAULT_MINIMUM_IV_HISTORY_DAYS,
        iv_warning_threshold: float | None = None,
        iv_reject_threshold: float | None = None,
    ) -> None:
        self.minimum_history_days = minimum_history_days
        self._override_warning_threshold = iv_warning_threshold
        self._override_reject_threshold = iv_reject_threshold

    def ensure_tables(self, db: Session) -> None:
        ensure_tables(db)

    def compute_for_symbol(
        self,
        db: Session,
        symbol: str,
        now: datetime | None = None,
    ) -> IvRiskComputation:
        self.ensure_tables(db)

        current_time = now or datetime.now(timezone.utc)
        snapshot_date = current_time.date()
        clean_symbol = symbol.upper()

        active_profile = profile_manager.get_active_profile()
        warning_threshold = (
            float(self._override_warning_threshold)
            if self._override_warning_threshold is not None
            else float(active_profile.iv_warning_threshold)
        )
        reject_threshold = (
            float(self._override_reject_threshold)
            if self._override_reject_threshold is not None
            else float(active_profile.iv_reject_threshold)
        )

        rows = (
            db.query(IvHistoryDay)
            .filter(IvHistoryDay.symbol == clean_symbol)
            .order_by(IvHistoryDay.snapshot_date.asc())
            .all()
        )

        if not rows:
            return IvRiskComputation(
                symbol=clean_symbol,
                snapshot_date=snapshot_date,
                current_iv=None,
                iv_rank=None,
                iv_percentile=None,
                iv_history_days_used=0,
                iv_warning_threshold=warning_threshold,
                iv_reject_threshold=reject_threshold,
                risk_label=RISK_LABEL_IV_DATA_NOT_AVAILABLE,
                risk_reason=(
                    "No IV history rows are stored for this symbol. "
                    "Stock-level research continues without an IV constraint."
                ),
                data_sufficiency_status="IV_DATA_NOT_AVAILABLE",
            )

        historical_ivs = [float(row.atm_iv_30d) for row in rows]
        current_iv = historical_ivs[-1]

        if len(historical_ivs) < self.minimum_history_days:
            return IvRiskComputation(
                symbol=clean_symbol,
                snapshot_date=snapshot_date,
                current_iv=current_iv,
                iv_rank=None,
                iv_percentile=None,
                iv_history_days_used=len(historical_ivs),
                iv_warning_threshold=warning_threshold,
                iv_reject_threshold=reject_threshold,
                risk_label=RISK_LABEL_INSUFFICIENT_IV_HISTORY,
                risk_reason=(
                    f"IV history has {len(historical_ivs)} rows but "
                    f"{self.minimum_history_days} are required to compute "
                    "rank/percentile."
                ),
                data_sufficiency_status="INSUFFICIENT_IV_HISTORY",
            )

        # Use all rows except the last one (treated as "current") as history
        history_for_ranking = historical_ivs[:-1]
        if len(history_for_ranking) < self.minimum_history_days:
            # Fall back to using the full series — rank/percentile are still
            # well-defined and the difference is only at the tail point.
            history_for_ranking = historical_ivs

        iv_rank = calculate_iv_rank(
            current_iv=current_iv,
            historical_ivs=history_for_ranking,
            minimum_history_days=self.minimum_history_days,
        )
        iv_percentile = calculate_iv_percentile(
            current_iv=current_iv,
            historical_ivs=history_for_ranking,
            minimum_history_days=self.minimum_history_days,
        )

        if iv_rank is None or iv_percentile is None:
            return IvRiskComputation(
                symbol=clean_symbol,
                snapshot_date=snapshot_date,
                current_iv=current_iv,
                iv_rank=iv_rank,
                iv_percentile=iv_percentile,
                iv_history_days_used=len(historical_ivs),
                iv_warning_threshold=warning_threshold,
                iv_reject_threshold=reject_threshold,
                risk_label=RISK_LABEL_INSUFFICIENT_IV_HISTORY,
                risk_reason=(
                    "IV rank/percentile could not be computed even with the "
                    "available history."
                ),
                data_sufficiency_status="INSUFFICIENT_IV_HISTORY",
            )

        risk_label, risk_reason = self._classify_label(
            iv_rank=iv_rank,
            warning_threshold=warning_threshold,
            reject_threshold=reject_threshold,
        )

        return IvRiskComputation(
            symbol=clean_symbol,
            snapshot_date=snapshot_date,
            current_iv=current_iv,
            iv_rank=iv_rank,
            iv_percentile=iv_percentile,
            iv_history_days_used=len(historical_ivs),
            iv_warning_threshold=warning_threshold,
            iv_reject_threshold=reject_threshold,
            risk_label=risk_label,
            risk_reason=risk_reason,
            data_sufficiency_status="SUFFICIENT",
        )

    def _classify_label(
        self,
        iv_rank: float,
        warning_threshold: float,
        reject_threshold: float,
    ) -> tuple[str, str]:
        if iv_rank >= reject_threshold:
            return (
                RISK_LABEL_IV_REJECT,
                f"IV rank {iv_rank:.1f} is at or above reject threshold "
                f"{reject_threshold:.1f}.",
            )
        if iv_rank >= warning_threshold:
            return (
                RISK_LABEL_IV_WARNING,
                f"IV rank {iv_rank:.1f} is at or above warning threshold "
                f"{warning_threshold:.1f}.",
            )
        return (
            RISK_LABEL_IV_LOW,
            f"IV rank {iv_rank:.1f} is below warning threshold "
            f"{warning_threshold:.1f}.",
        )

    def persist_snapshot(
        self,
        db: Session,
        computation: IvRiskComputation,
    ) -> tuple[IvRiskSnapshot, bool]:
        self.ensure_tables(db)

        existing = (
            db.query(IvRiskSnapshot)
            .filter(IvRiskSnapshot.symbol == computation.symbol)
            .filter(IvRiskSnapshot.snapshot_date == computation.snapshot_date)
            .one_or_none()
        )

        values = {
            "current_iv": computation.current_iv,
            "iv_rank": computation.iv_rank,
            "iv_percentile": computation.iv_percentile,
            "iv_history_days_used": computation.iv_history_days_used,
            "iv_warning_threshold": computation.iv_warning_threshold,
            "iv_reject_threshold": computation.iv_reject_threshold,
            "risk_label": computation.risk_label,
            "risk_reason": computation.risk_reason,
            "data_sufficiency_status": computation.data_sufficiency_status,
        }

        if existing is None:
            row = IvRiskSnapshot(
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

    def refresh_iv_risk(
        self,
        db: Session,
        symbols: list[str] | None = None,
        now: datetime | None = None,
    ) -> IvRiskRefreshResult:
        self.ensure_tables(db)

        normalized = self._normalize_symbols(symbols or [])
        result = IvRiskRefreshResult(requested_symbols=normalized)

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

            if computation.risk_label == RISK_LABEL_IV_DATA_NOT_AVAILABLE:
                result.no_data_symbols.append(symbol)
            elif computation.risk_label == RISK_LABEL_INSUFFICIENT_IV_HISTORY:
                result.insufficient_symbols.append(symbol)
            else:
                result.successful_symbols.append(symbol)

            if inserted:
                result.snapshots_inserted += 1
            else:
                result.snapshots_updated += 1

        db.commit()
        return result

    def _normalize_symbols(self, symbols: list[str]) -> list[str]:
        return normalize_symbols(symbols)


__all__ = [
    "DEFAULT_MINIMUM_IV_HISTORY_DAYS",
    "IvRiskComputation",
    "IvRiskRefreshResult",
    "IvRiskService",
    "RISK_LABEL_INSUFFICIENT_IV_HISTORY",
    "RISK_LABEL_IV_DATA_NOT_AVAILABLE",
    "RISK_LABEL_IV_LOW",
    "RISK_LABEL_IV_REJECT",
    "RISK_LABEL_IV_WARNING",
]
