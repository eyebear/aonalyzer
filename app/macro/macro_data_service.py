from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol

from sqlalchemy.orm import Session

from app.data_quality.data_quality_models import DataFreshness
from app.data_quality.data_sufficiency_labels import DataFreshnessStatus
from app.event_normalizer.event_labels import EventDataCategory
from app.event_normalizer.event_normalizer import EventNormalizer
from app.macro.sources.econ_calendar_source import EconCalendarSource


class MacroSource(Protocol):
    source_id: str
    source_name: str

    def fetch_macro_events(self) -> list[dict[str, Any]]: ...


@dataclass
class MacroRefreshResult:
    sources_used: list[str] = field(default_factory=list)

    items_fetched: int = 0
    items_normalized: int = 0
    events_inserted: int = 0
    duplicate_events: int = 0
    rejected_items: int = 0

    failed_sources: list[str] = field(default_factory=list)
    failed_reasons: dict[str, str] = field(default_factory=dict)

    @property
    def records_created(self) -> int:
        return self.events_inserted

    @property
    def records_updated(self) -> int:
        return 0

    @property
    def records_failed(self) -> int:
        return len(self.failed_sources)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sources_used": self.sources_used,
            "items_fetched": self.items_fetched,
            "items_normalized": self.items_normalized,
            "events_inserted": self.events_inserted,
            "duplicate_events": self.duplicate_events,
            "rejected_items": self.rejected_items,
            "records_created": self.records_created,
            "records_updated": self.records_updated,
            "records_failed": self.records_failed,
            "failed_sources": self.failed_sources,
            "failed_reasons": self.failed_reasons,
        }


class MacroDataService:
    data_category = EventDataCategory.MACRO.value
    default_freshness_minutes = 720

    def __init__(
        self,
        sources: list[MacroSource] | None = None,
        normalizer: EventNormalizer | None = None,
    ) -> None:
        self.sources = (
            sources if sources is not None else [EconCalendarSource()]
        )
        self.normalizer = normalizer or EventNormalizer()

    def refresh_macro_events(self, db: Session) -> MacroRefreshResult:
        result = MacroRefreshResult(
            sources_used=[source.source_id for source in self.sources],
        )

        now = datetime.now(timezone.utc)

        for source in self.sources:
            try:
                raw_items = source.fetch_macro_events()
            except Exception as exc:
                result.failed_sources.append(source.source_id)
                result.failed_reasons[source.source_id] = str(exc)
                continue

            if not raw_items:
                continue

            result.items_fetched += len(raw_items)

            normalization = self.normalizer.normalize_batch(
                raw_events=raw_items,
                default_event_type="MACRO",
                default_source=source.source_id,
                symbol=None,
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

        status = (
            DataFreshnessStatus.FRESH
            if result.events_inserted > 0 or result.items_fetched > 0
            else DataFreshnessStatus.MISSING
        )

        self._update_data_freshness(
            db=db,
            status=status,
            details=result.to_dict(),
        )

        db.commit()
        return result

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


__all__ = [
    "MacroDataService",
    "MacroRefreshResult",
    "MacroSource",
]
