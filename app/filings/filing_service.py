from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol

from sqlalchemy.orm import Session

from app.common.service_utils import normalize_symbols
from app.data_quality.data_quality_models import DataFreshness
from app.data_quality.data_sufficiency_labels import DataFreshnessStatus
from app.event_normalizer.event_labels import EventDataCategory
from app.event_normalizer.event_normalizer import EventNormalizer
from app.filings.sources.sec_edgar_source import SecEdgarFilingSource


class FilingSource(Protocol):
    source_id: str
    source_name: str

    def fetch_ticker_filings(self, symbol: str) -> list[dict[str, Any]]: ...


@dataclass
class FilingRefreshResult:
    requested_symbols: list[str] = field(default_factory=list)
    successful_symbols: list[str] = field(default_factory=list)
    failed_symbols: list[str] = field(default_factory=list)

    sources_used: list[str] = field(default_factory=list)

    items_fetched: int = 0
    items_normalized: int = 0
    events_inserted: int = 0
    duplicate_events: int = 0
    rejected_items: int = 0

    failed_reasons: dict[str, str] = field(default_factory=dict)

    @property
    def records_created(self) -> int:
        return self.events_inserted

    @property
    def records_updated(self) -> int:
        return 0

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
            "items_normalized": self.items_normalized,
            "events_inserted": self.events_inserted,
            "duplicate_events": self.duplicate_events,
            "rejected_items": self.rejected_items,
            "records_created": self.records_created,
            "records_updated": self.records_updated,
            "records_failed": self.records_failed,
            "failed_reasons": self.failed_reasons,
        }


class FilingService:
    data_category = EventDataCategory.FILINGS.value
    default_freshness_minutes = 240

    def __init__(
        self,
        sources: list[FilingSource] | None = None,
        normalizer: EventNormalizer | None = None,
    ) -> None:
        self.sources = (
            sources if sources is not None else [SecEdgarFilingSource()]
        )
        self.normalizer = normalizer or EventNormalizer()

    def refresh_ticker_filings(
        self,
        db: Session,
        symbols: list[str] | None = None,
    ) -> FilingRefreshResult:
        normalized_symbols = self._normalize_symbols(symbols or [])

        result = FilingRefreshResult(
            requested_symbols=normalized_symbols,
            sources_used=[source.source_id for source in self.sources],
        )

        if not normalized_symbols:
            self._update_data_freshness(
                db=db,
                status=DataFreshnessStatus.MISSING,
                details={
                    "reason": "No symbols supplied for filings refresh.",
                    **result.to_dict(),
                },
            )
            db.commit()
            return result

        now = datetime.now(timezone.utc)

        for symbol in normalized_symbols:
            try:
                self._refresh_one_symbol(
                    db=db,
                    symbol=symbol,
                    result=result,
                    now=now,
                )
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
        result: FilingRefreshResult,
        now: datetime,
    ) -> None:
        for source in self.sources:
            try:
                raw_items = source.fetch_ticker_filings(symbol)
            except Exception as exc:
                result.failed_reasons[f"{symbol}:{source.source_id}"] = str(exc)
                continue

            if not raw_items:
                continue

            result.items_fetched += len(raw_items)

            normalization = self.normalizer.normalize_batch(
                raw_events=raw_items,
                default_event_type="FILING",
                default_source=source.source_id,
                symbol=symbol,
                now=now,
            )

            result.items_normalized += len(normalization.normalized)
            result.rejected_items += len(normalization.rejected)

            persist_result = self.normalizer.persist_events(
                db=db,
                events=normalization.normalized,
            )

            result.events_inserted += persist_result.inserted_count
            result.duplicate_events += persist_result.duplicate_count

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

    def _normalize_symbols(self, symbols: list[str]) -> list[str]:
        return normalize_symbols(symbols)


__all__ = [
    "FilingRefreshResult",
    "FilingService",
    "FilingSource",
]
