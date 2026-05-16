from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Protocol
from urllib.request import Request, urlopen


class RssFetcher(Protocol):
    def fetch(self, url: str, timeout: int = 15) -> list[dict[str, Any]]: ...


class FeedparserRssFetcher:
    """RSS fetcher backed by ``feedparser`` with safe fallbacks.

    Returns an empty list when the source is unavailable, slow, blocked,
    malformed, or returns unexpected data. Never raises to the caller.
    """

    def __init__(self, user_agent: str = "Mozilla/5.0 (Aonalyzer)") -> None:
        self.user_agent = user_agent

    def fetch(self, url: str, timeout: int = 15) -> list[dict[str, Any]]:
        raw_bytes = self._download(url, timeout=timeout)

        if raw_bytes is None:
            return []

        return self._parse(raw_bytes)

    def _download(self, url: str, timeout: int) -> bytes | None:
        try:
            request = Request(
                url,
                headers={
                    "User-Agent": self.user_agent,
                    "Accept": "application/rss+xml,application/xml,text/xml,*/*",
                },
            )
            with urlopen(request, timeout=timeout) as response:
                return response.read()
        except Exception:
            return None

    def _parse(self, raw_bytes: bytes) -> list[dict[str, Any]]:
        try:
            import feedparser
        except Exception:
            return []

        try:
            feed = feedparser.parse(raw_bytes)
        except Exception:
            return []

        entries = getattr(feed, "entries", None)

        if not entries:
            return []

        items: list[dict[str, Any]] = []

        for entry in entries:
            try:
                items.append(self._entry_to_dict(entry))
            except Exception:
                continue

        return items

    def _entry_to_dict(self, entry: Any) -> dict[str, Any]:
        title = self._get_attr(entry, "title") or ""
        link = self._get_attr(entry, "link") or ""
        summary = (
            self._get_attr(entry, "summary")
            or self._get_attr(entry, "description")
            or ""
        )
        source_name = ""

        source_struct = self._get_attr(entry, "source")
        if isinstance(source_struct, dict):
            source_name = source_struct.get("title") or source_struct.get("href") or ""
        elif source_struct:
            source_name = str(source_struct)

        published_time = self._extract_published_time(entry)

        return {
            "title": str(title).strip(),
            "link": str(link).strip(),
            "summary": str(summary).strip(),
            "source_title": str(source_name).strip(),
            "published": published_time,
        }

    def _get_attr(self, entry: Any, key: str) -> Any:
        if isinstance(entry, dict):
            return entry.get(key)
        return getattr(entry, key, None)

    def _extract_published_time(self, entry: Any) -> datetime | None:
        for field in ("published_parsed", "updated_parsed"):
            struct = self._get_attr(entry, field)
            if struct is None:
                continue

            try:
                return datetime(
                    struct.tm_year,
                    struct.tm_mon,
                    struct.tm_mday,
                    struct.tm_hour,
                    struct.tm_min,
                    struct.tm_sec,
                    tzinfo=timezone.utc,
                )
            except Exception:
                continue

        for field in ("published", "updated"):
            iso = self._get_attr(entry, field)
            if not iso:
                continue

            try:
                parsed = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
            except ValueError:
                continue

            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)

            return parsed

        return None
