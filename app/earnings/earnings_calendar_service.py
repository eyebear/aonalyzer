from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol

from sqlalchemy.orm import Session

from app.common.service_utils import ensure_tables, normalize_symbols
from app.data_quality.data_quality_models import DataFreshness
from app.data_quality.data_sufficiency_labels import DataFreshnessStatus
from app.earnings.earnings_models import EarningsEvent
from app.earnings.sources.yahoo_earnings_source import YahooEarningsCalendarSource


class EarningsCalendarSource(Protocol):
    source_id: str
    source_name: str

    def fetch_ticker_earnings(self, symbol: str) -> list[dict[str, Any]]: ...


@dataclass
class EarningsCalendarRefreshResult:
    requested_symbols: list[str] = field(default_factory=list)
    successful_symbols: list[str] = field(default_factory=list)
    failed_symbols: list[str] = field(default_factory=list)

    sources_used: list[str] = field(default_factory=list)
    items_fetched: int = 0
    events_inserted: int = 0
    events_updated: int = 0
    rejected_items: int = 0

    failed_reasons: dict[str, str] = field(default_factory=dict)

    @property
    def records_created(self) -> int:
        return self.events_inserted

    @property
    def records_updated(self) -> int:
        return self.events_updated

    @property
    def records_failed(self) -> int:
        return len(self.failed_symbols)

    def to_dict(self) -> dict[str, Any]:
        return {
            "requested_symbols": self.requested_symbols,
            "successful_symbols": self.successful_symbols,
            "failed_symbols": self.failed_symbols,
            "sources_used": self.sources_used,
            "items_fetched": self.items_fetched,
            "events_inserted": self.events_inserted,
            "events_updated": self.events_updated,
            "rejected_items": self.rejected_items,
            "records_created": self.records_created,
            "records_updated": self.records_updated,
            "records_failed": self.records_failed,
            "failed_reasons": self.failed_reasons,
        }


class EarningsCalendarService:
    data_category = "earnings_calendar"
    default_freshness_minutes = 1440

    def __init__(
        self,
        sources: list[EarningsCalendarSource] | None = None,
    ) -> None:
        self.sources = (
            sources if sources is not None else [YahooEarningsCalendarSource()]
        )

    def ensure_tables(self, db: Session) -> None:
        ensure_tables(db)

    def refresh_ticker_earnings(
        self,
        db: Session,
        symbols: list[str] | None = None,
    ) -> EarningsCalendarRefreshResult:
        self.ensure_tables(db)

        normalized = self._normalize_symbols(symbols or [])

        result = EarningsCalendarRefreshResult(
            requested_symbols=normalized,
            sources_used=[s.source_id for s in self.sources],
        )

        if not normalized:
            self._update_data_freshness(
                db=db,
                status=DataFreshnessStatus.MISSING,
                details={
                    "reason": "No symbols supplied for earnings refresh.",
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
                continue

            if symbol not in result.failed_symbols:
                result.successful_symbols.append(symbol)

        status = (
            DataFreshnessStatus.FRESH
            if result.successful_symbols
            else DataFreshnessStatus.MISSING
        )
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
        result: EarningsCalendarRefreshResult,
    ) -> None:
        for source in self.sources:
            try:
                raw_items = source.fetch_ticker_earnings(symbol)
            except Exception as exc:
                result.failed_reasons[f"{symbol}:{source.source_id}"] = str(exc)
                continue

            if not raw_items:
                continue

            result.items_fetched += len(raw_items)

            for raw in raw_items:
                normalized = self._normalize_event(
                    raw=raw,
                    symbol=symbol,
                    source_id=source.source_id,
                )
                if normalized is None:
                    result.rejected_items += 1
                    continue

                inserted_or_updated = self._upsert_event(
                    db=db,
                    normalized=normalized,
                )
                if inserted_or_updated == "INSERTED":
                    result.events_inserted += 1
                elif inserted_or_updated == "UPDATED":
                    result.events_updated += 1

    def _normalize_event(
        self,
        raw: dict[str, Any],
        symbol: str,
        source_id: str,
    ) -> dict[str, Any] | None:
        earnings_datetime = self._coerce_datetime(
            raw.get("earnings_datetime_utc")
            or raw.get("earnings_datetime")
            or raw.get("datetime")
        )
        if earnings_datetime is None:
            return None

        time_of_day = (raw.get("time_of_day") or raw.get("when") or "UNKNOWN")
        time_of_day = str(time_of_day).strip().upper() or "UNKNOWN"
        if time_of_day not in ("BMO", "AMC", "DMH", "UNKNOWN"):
            time_of_day = "UNKNOWN"

        confirmed_raw = raw.get("confirmed", False)
        confirmed = bool(confirmed_raw)

        return {
            "symbol": symbol.upper(),
            "earnings_datetime_utc": earnings_datetime,
            "time_of_day": time_of_day,
            "confirmed": confirmed,
            "source": (raw.get("source") or source_id).strip(),
            "source_url": self._optional_str(raw.get("source_url") or raw.get("url")),
            "source_title": self._optional_str(
                raw.get("source_title") or raw.get("source_name")
            ),
            "event_metadata_json": raw.get("event_metadata") or {},
        }

    def _upsert_event(
        self,
        db: Session,
        normalized: dict[str, Any],
    ) -> str:
        existing = (
            db.query(EarningsEvent)
            .filter(EarningsEvent.symbol == normalized["symbol"])
            .filter(
                EarningsEvent.earnings_datetime_utc
                == normalized["earnings_datetime_utc"]
            )
            .filter(EarningsEvent.source == normalized["source"])
            .one_or_none()
        )

        if existing is None:
            db.add(EarningsEvent(**normalized))
            db.flush()
            return "INSERTED"

        existing.time_of_day = normalized["time_of_day"]
        existing.confirmed = normalized["confirmed"]
        existing.source_url = normalized["source_url"]
        existing.source_title = normalized["source_title"]
        existing.event_metadata_json = normalized["event_metadata_json"]
        db.flush()
        return "UPDATED"

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

    def _coerce_datetime(self, value: Any) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return (
                value
                if value.tzinfo is not None
                else value.replace(tzinfo=timezone.utc)
            )
        text_value = str(value).strip()
        if not text_value:
            return None
        try:
            parsed = datetime.fromisoformat(text_value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed

    def _optional_str(self, value: Any) -> str | None:
        if value is None:
            return None
        text_value = str(value).strip()
        return text_value or None

    def _normalize_symbols(self, symbols: list[str]) -> list[str]:
        return normalize_symbols(symbols)


__all__ = [
    "EarningsCalendarRefreshResult",
    "EarningsCalendarService",
    "EarningsCalendarSource",
]
