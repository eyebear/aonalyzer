from __future__ import annotations

import hashlib
import re
from datetime import datetime

_WHITESPACE_PATTERN = re.compile(r"\s+")


def normalize_headline(headline: str | None) -> str:
    if headline is None:
        return ""

    stripped = headline.strip().lower()
    return _WHITESPACE_PATTERN.sub(" ", stripped)


def normalize_source_url(source_url: str | None) -> str:
    if source_url is None:
        return ""

    return source_url.strip().lower()


def build_content_hash(
    event_type: str,
    source: str,
    headline: str | None,
    symbol: str | None = None,
    source_url: str | None = None,
    event_time: datetime | None = None,
) -> str:
    """Deterministic SHA-256 hash for event deduplication.

    Including ``symbol`` lets the same multi-ticker story produce one row per
    ticker while still deduping within a (source, symbol) pair.

    ``event_time`` is accepted but intentionally ignored so minor time drift
    on re-fetch still dedupes against the original row.
    """
    _ = event_time  # signal: time intentionally excluded from hash

    parts = [
        (event_type or "").strip().upper(),
        (source or "").strip().lower(),
        (symbol or "").strip().upper(),
        normalize_source_url(source_url),
        normalize_headline(headline),
    ]

    payload = "|".join(parts).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
