from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Protocol

from sqlalchemy.orm import Session

from app.common.service_utils import ensure_tables, normalize_symbols
from app.data_quality.data_quality_models import DataFreshness
from app.data_quality.data_sufficiency_labels import DataFreshnessStatus
from app.iv_history.iv_models import IvHistoryDay
from app.iv_history.sources.iv_history_source import PlaceholderIvHistorySource


class IvHistorySource(Protocol):
    source_id: str
    source_name: str

    def fetch_ticker_iv_history(self, symbol: str) -> list[dict[str, Any]]: ...


@dataclass
class IvHistoryRefreshResult:
    requested_symbols: list[str] = field(default_factory=list)
    successful_symbols: list[str] = field(default_factory=list)
    no_data_symbols: list[str] = field(default_factory=list)
    failed_symbols: list[str] = field(default_factory=list)

    sources_used: list[str] = field(default_factory=list)
    items_fetched: int = 0
    rows_inserted: int = 0
    rows_updated: int = 0
    rejected_items: int = 0

    failed_reasons: dict[str, str] = field(default_factory=dict)

    @property
    def records_created(self) -> int:
        return self.rows_inserted

    @property
    def records_updated(self) -> int:
        return self.rows_updated

    @property
    def records_failed(self) -> int:
        return len(self.failed_symbols)

    def to_dict(self) -> dict[str, Any]:
        return {
            "requested_symbols": self.requested_symbols,
            "successful_symbols": self.successful_symbols,
            "no_data_symbols": self.no_data_symbols,
            "failed_symbols": self.failed_symbols,
            "sources_used": self.sources_used,
            "items_fetched": self.items_fetched,
            "rows_inserted": self.rows_inserted,
            "rows_updated": self.rows_updated,
            "rejected_items": self.rejected_items,
            "records_created": self.records_created,
            "records_updated": self.records_updated,
            "records_failed": self.records_failed,
            "failed_reasons": self.failed_reasons,
        }


class IvHistoryService:
    """Optional IV history collector.

    IV history is **never** a hard dependency in Aonalyzer. When a source
    returns no rows, the freshness write reflects that cleanly and downstream
    IV-risk computation surfaces ``IV_DATA_NOT_AVAILABLE``. No fake values
    are ever invented.
    """

    data_category = "iv_history"
    default_freshness_minutes = 1440

    def __init__(
        self,
        sources: list[IvHistorySource] | None = None,
    ) -> None:
        self.sources = (
            sources if sources is not None else [PlaceholderIvHistorySource()]
        )

    def ensure_tables(self, db: Session) -> None:
        ensure_tables(db)

    def refresh_ticker_iv_history(
        self,
        db: Session,
        symbols: list[str] | None = None,
    ) -> IvHistoryRefreshResult:
        self.ensure_tables(db)

        normalized = self._normalize_symbols(symbols or [])

        result = IvHistoryRefreshResult(
            requested_symbols=normalized,
            sources_used=[s.source_id for s in self.sources],
        )

        if not normalized:
            self._update_data_freshness(
                db=db,
                status=DataFreshnessStatus.MISSING,
                details={
                    "reason": "No symbols supplied for IV history refresh.",
                    **result.to_dict(),
                },
            )
            db.commit()
            return result

        for symbol in normalized:
            try:
                self._refresh_one_symbol(db=db, symbol=symbol, result=result)
            except Exception as exc:
                result.failed_symbols.append(symbol)
                result.failed_reasons[symbol] = str(exc)

        # Mark freshness based on insertion success across the batch.
        if result.records_created > 0 or result.records_updated > 0:
            status = DataFreshnessStatus.FRESH
        else:
            status = DataFreshnessStatus.MISSING

        self._update_data_freshness(
            db=db,
            status=status,
            details=result.to_dict(),
        )
        db.commit()
        return result

    def _refresh_one_symbol(
        self,
        db: Session,
        symbol: str,
        result: IvHistoryRefreshResult,
    ) -> None:
        any_inserted = False

        for source in self.sources:
            try:
                raw_items = source.fetch_ticker_iv_history(symbol)
            except Exception as exc:
                result.failed_reasons[f"{symbol}:{source.source_id}"] = str(exc)
                continue

            if not raw_items:
                continue

            result.items_fetched += len(raw_items)

            for raw in raw_items:
                normalized = self._normalize_row(
                    raw=raw,
                    symbol=symbol,
                    source_id=source.source_id,
                )
                if normalized is None:
                    result.rejected_items += 1
                    continue

                action = self._upsert_row(db=db, normalized=normalized)
                if action == "INSERTED":
                    result.rows_inserted += 1
                    any_inserted = True
                elif action == "UPDATED":
                    result.rows_updated += 1
                    any_inserted = True

        if any_inserted:
            result.successful_symbols.append(symbol)
        elif symbol not in result.failed_symbols:
            result.no_data_symbols.append(symbol)

    def _normalize_row(
        self,
        raw: dict[str, Any],
        symbol: str,
        source_id: str,
    ) -> dict[str, Any] | None:
        snapshot_date = self._coerce_date(
            raw.get("snapshot_date") or raw.get("date")
        )
        atm_iv = raw.get("atm_iv_30d") or raw.get("iv") or raw.get("atm_iv")

        if snapshot_date is None or atm_iv is None:
            return None

        try:
            iv_value = float(atm_iv)
        except (TypeError, ValueError):
            return None

        if iv_value <= 0:
            return None

        return {
            "symbol": symbol.upper(),
            "snapshot_date": snapshot_date,
            "atm_iv_30d": iv_value,
            "source": (raw.get("source") or source_id).strip(),
            "source_url": self._optional_str(raw.get("source_url") or raw.get("url")),
            "metadata_json": raw.get("metadata") or {},
        }

    def _upsert_row(
        self,
        db: Session,
        normalized: dict[str, Any],
    ) -> str:
        existing = (
            db.query(IvHistoryDay)
            .filter(IvHistoryDay.symbol == normalized["symbol"])
            .filter(IvHistoryDay.snapshot_date == normalized["snapshot_date"])
            .one_or_none()
        )

        if existing is None:
            db.add(IvHistoryDay(**normalized))
            db.flush()
            return "INSERTED"

        existing.atm_iv_30d = normalized["atm_iv_30d"]
        existing.source = normalized["source"]
        existing.source_url = normalized["source_url"]
        existing.metadata_json = normalized["metadata_json"]
        db.flush()
        return "UPDATED"

    def list_history(
        self,
        db: Session,
        symbol: str,
        since: date | None = None,
        limit: int = 500,
    ) -> list[IvHistoryDay]:
        self.ensure_tables(db)

        query = db.query(IvHistoryDay).filter(IvHistoryDay.symbol == symbol.upper())
        if since is not None:
            query = query.filter(IvHistoryDay.snapshot_date >= since)

        return (
            query.order_by(IvHistoryDay.snapshot_date.desc())
            .limit(limit)
            .all()
        )

    def _update_data_freshness(
        self,
        db: Session,
        status: DataFreshnessStatus,
        details: dict[str, Any] | None = None,
    ) -> None:
        now = datetime.now(timezone.utc)

        existing = (
            db.query(DataFreshness)
            .filter(DataFreshness.data_category == self.data_category)
            .one_or_none()
        )

        if existing is None:
            db.add(
                DataFreshness(
                    data_category=self.data_category,
                    latest_success_at=now
                    if status == DataFreshnessStatus.FRESH
                    else None,
                    freshness_status=status.value,
                    max_age_minutes=self.default_freshness_minutes,
                    last_checked_at=now,
                    details_json=details or {},
                )
            )
            return

        if status == DataFreshnessStatus.FRESH:
            existing.latest_success_at = now

        existing.freshness_status = status.value
        existing.last_checked_at = now
        existing.details_json = details or {}

    def _coerce_date(self, value: Any) -> date | None:
        if value is None:
            return None
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        if isinstance(value, datetime):
            return value.date()
        text_value = str(value).strip()
        if not text_value:
            return None
        try:
            return datetime.fromisoformat(text_value[:10]).date()
        except ValueError:
            return None

    def _optional_str(self, value: Any) -> str | None:
        if value is None:
            return None
        text_value = str(value).strip()
        return text_value or None

    def _normalize_symbols(self, symbols: list[str]) -> list[str]:
        return normalize_symbols(symbols)


__all__ = [
    "IvHistoryRefreshResult",
    "IvHistoryService",
    "IvHistorySource",
]
