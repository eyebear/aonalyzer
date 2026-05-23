"""Phase 36 — News / Events page helpers (pure, deterministic, testable).

Reuses normalized events (no re-ingestion). The date-window and field filters
are deterministic so they can be unit-tested. Source links are surfaced only
when present.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

# Date-window options -> hours (None = all time).
DATE_WINDOWS: dict[str, int | None] = {
    "24h": 24,
    "7d": 24 * 7,
    "30d": 24 * 30,
    "all": None,
}


def _coerce_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def filter_events(
    events: list[dict[str, Any]],
    *,
    date_window: str = "all",
    symbol: str | None = None,
    event_type: str | None = None,
    importance_level: str | None = None,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Deterministically filter event dicts by window / ticker / type / importance."""
    now = now or datetime.now(timezone.utc)
    hours = DATE_WINDOWS.get(date_window, None)
    cutoff = now - timedelta(hours=hours) if hours is not None else None

    symbol_u = symbol.strip().upper() if symbol else None
    type_u = event_type.strip().upper() if event_type and event_type != "(any)" else None
    imp_u = (
        importance_level.strip().upper()
        if importance_level and importance_level != "(any)"
        else None
    )

    out: list[dict[str, Any]] = []
    for event in events:
        if symbol_u and (event.get("symbol") or "").upper() != symbol_u:
            continue
        if type_u and (event.get("event_type") or "").upper() != type_u:
            continue
        if imp_u and (event.get("importance_level") or "").upper() != imp_u:
            continue
        if cutoff is not None:
            event_dt = _coerce_dt(event.get("event_time") or event.get("detected_time"))
            # Events without a timestamp are conservatively kept.
            if event_dt is not None and event_dt < cutoff:
                continue
        out.append(event)
    return out


def build_event_row(event: dict[str, Any]) -> dict[str, Any]:
    """Display row for one event. Source link only when available."""
    metadata = event.get("event_metadata") or {}
    return {
        "id": event.get("id"),
        "symbol": event.get("symbol"),
        "event_type": event.get("event_type"),
        "importance_level": event.get("importance_level"),
        "headline": event.get("headline") or event.get("source_title"),
        "source_url": event.get("source_url"),  # may be None
        "has_source_link": bool(event.get("source_url")),
        "ai_summary": metadata.get("ai_summary") or event.get("ai_summary"),
        "price_in_assessment": metadata.get("price_in_assessment"),
        "is_reviewed": bool(event.get("is_reviewed")),
        "event_time": event.get("event_time"),
    }


__all__ = ["DATE_WINDOWS", "build_event_row", "filter_events"]
