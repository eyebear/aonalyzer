from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.database.models import Event
from app.event_normalizer.content_hash import build_content_hash
from app.event_normalizer.event_labels import (
    KNOWN_EVENT_TYPES,
    KNOWN_IMPORTANCE_LEVELS,
)
from app.event_normalizer.importance_classifier import ImportanceClassifier


@dataclass(frozen=True)
class NormalizedEvent:
    event_type: str
    source: str
    headline: str
    raw_summary: str | None
    source_url: str | None
    source_title: str | None
    symbol: str | None
    market: str | None
    event_time: datetime | None
    importance_level: str
    importance_reason: str
    content_hash: str
    event_metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type,
            "source": self.source,
            "headline": self.headline,
            "raw_summary": self.raw_summary,
            "source_url": self.source_url,
            "source_title": self.source_title,
            "symbol": self.symbol,
            "market": self.market,
            "event_time": self.event_time.isoformat()
            if self.event_time is not None
            else None,
            "importance_level": self.importance_level,
            "importance_reason": self.importance_reason,
            "content_hash": self.content_hash,
            "event_metadata": self.event_metadata,
        }


@dataclass
class NormalizationResult:
    normalized: list[NormalizedEvent] = field(default_factory=list)
    rejected: list[dict[str, Any]] = field(default_factory=list)

    def add_normalized(self, event: NormalizedEvent) -> None:
        self.normalized.append(event)

    def add_rejected(self, raw: dict[str, Any], reason: str) -> None:
        self.rejected.append(
            {
                "reason": reason,
                "raw": raw,
            }
        )


@dataclass
class EventPersistResult:
    inserted_hashes: list[str] = field(default_factory=list)
    duplicate_hashes: list[str] = field(default_factory=list)

    @property
    def inserted_count(self) -> int:
        return len(self.inserted_hashes)

    @property
    def duplicate_count(self) -> int:
        return len(self.duplicate_hashes)

    def to_dict(self) -> dict[str, Any]:
        return {
            "inserted_count": self.inserted_count,
            "duplicate_count": self.duplicate_count,
            "inserted_hashes": self.inserted_hashes,
            "duplicate_hashes": self.duplicate_hashes,
        }


class EventNormalizer:
    def __init__(
        self,
        classifier: ImportanceClassifier | None = None,
    ) -> None:
        self.classifier = classifier or ImportanceClassifier()

    def normalize_raw_event(
        self,
        raw_event: dict[str, Any],
        default_event_type: str | None = None,
        default_source: str | None = None,
        symbol: str | None = None,
        now: datetime | None = None,
    ) -> NormalizedEvent | None:
        event_type = (
            raw_event.get("event_type")
            or default_event_type
            or ""
        ).strip().upper()

        if not event_type or event_type not in KNOWN_EVENT_TYPES:
            return None

        source = (
            raw_event.get("source")
            or default_source
            or ""
        ).strip()

        headline = (raw_event.get("headline") or raw_event.get("title") or "").strip()

        if not source or not headline:
            return None

        raw_summary = self._optional_str(
            raw_event.get("raw_summary") or raw_event.get("summary")
        )
        source_url = self._optional_str(
            raw_event.get("source_url")
            or raw_event.get("url")
            or raw_event.get("link")
        )
        source_title = self._optional_str(
            raw_event.get("source_title") or raw_event.get("source_name")
        )
        market = self._optional_str(raw_event.get("market"))

        normalized_symbol = self._normalize_symbol(
            raw_event.get("symbol") or symbol
        )

        event_time = self._coerce_datetime(raw_event.get("event_time"))

        explicit_importance = self._normalize_importance(
            raw_event.get("importance_level")
        )

        if explicit_importance is not None:
            importance_level = explicit_importance
            importance_reason = "importance_level supplied by source"
        else:
            verdict = self.classifier.classify(
                event_type=event_type,
                headline=headline,
                source=source,
                event_time=event_time,
                filing_type=self._optional_str(raw_event.get("filing_type")),
                now=now,
            )
            importance_level = verdict.level.value
            importance_reason = verdict.reason

        content_hash = build_content_hash(
            event_type=event_type,
            source=source,
            headline=headline,
            symbol=normalized_symbol,
            source_url=source_url,
            event_time=None,
        )

        metadata = dict(raw_event.get("event_metadata") or {})
        metadata.setdefault("importance_reason", importance_reason)

        filing_type = self._optional_str(raw_event.get("filing_type"))
        if filing_type:
            metadata.setdefault("filing_type", filing_type.upper())

        return NormalizedEvent(
            event_type=event_type,
            source=source,
            headline=headline,
            raw_summary=raw_summary,
            source_url=source_url,
            source_title=source_title,
            symbol=normalized_symbol,
            market=market,
            event_time=event_time,
            importance_level=importance_level,
            importance_reason=importance_reason,
            content_hash=content_hash,
            event_metadata=metadata,
        )

    def normalize_batch(
        self,
        raw_events: list[dict[str, Any]],
        default_event_type: str | None = None,
        default_source: str | None = None,
        symbol: str | None = None,
        now: datetime | None = None,
    ) -> NormalizationResult:
        result = NormalizationResult()

        for raw_event in raw_events or []:
            try:
                normalized = self.normalize_raw_event(
                    raw_event=raw_event,
                    default_event_type=default_event_type,
                    default_source=default_source,
                    symbol=symbol,
                    now=now,
                )
            except Exception as exc:
                result.add_rejected(raw_event, f"normalization error: {exc}")
                continue

            if normalized is None:
                result.add_rejected(raw_event, "missing event_type, source, or headline")
                continue

            result.add_normalized(normalized)

        return result

    def persist_events(
        self,
        db: Session,
        events: list[NormalizedEvent],
    ) -> EventPersistResult:
        result = EventPersistResult()

        if not events:
            return result

        seen_in_batch: set[str] = set()

        for event in events:
            if event.content_hash in seen_in_batch:
                result.duplicate_hashes.append(event.content_hash)
                continue

            seen_in_batch.add(event.content_hash)

            existing = (
                db.query(Event)
                .filter(Event.content_hash == event.content_hash)
                .one_or_none()
            )

            if existing is not None:
                result.duplicate_hashes.append(event.content_hash)
                continue

            db.add(
                Event(
                    event_time=event.event_time,
                    detected_time=datetime.now(timezone.utc),
                    source=event.source,
                    source_url=event.source_url,
                    source_title=event.source_title,
                    symbol=event.symbol,
                    market=event.market,
                    event_type=event.event_type,
                    importance_level=event.importance_level,
                    headline=event.headline,
                    raw_summary=event.raw_summary,
                    content_hash=event.content_hash,
                    event_metadata_json=event.event_metadata or {},
                    is_reviewed=False,
                )
            )

            result.inserted_hashes.append(event.content_hash)

        db.flush()
        return result

    def _normalize_symbol(self, value: Any) -> str | None:
        if value is None:
            return None

        text = str(value).strip().upper()
        return text or None

    def _optional_str(self, value: Any) -> str | None:
        if value is None:
            return None

        text = str(value).strip()
        return text or None

    def _normalize_importance(self, value: Any) -> str | None:
        if value is None:
            return None

        text = str(value).strip().upper()

        if text in KNOWN_IMPORTANCE_LEVELS:
            return text

        return None

    def _coerce_datetime(self, value: Any) -> datetime | None:
        if value is None:
            return None

        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value

        text = str(value).strip()

        if not text:
            return None

        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None

        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)

        return parsed
