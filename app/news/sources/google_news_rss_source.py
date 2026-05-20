from __future__ import annotations

from typing import Any
from urllib.parse import quote_plus

from app.news.sources.rss_fetcher import FeedparserRssFetcher, RssFetcher

GOOGLE_NEWS_RSS_BASE = "https://news.google.com/rss/search"


class GoogleNewsRssSource:
    """Ticker-aware Google News RSS source.

    Returns an empty list on any failure. The caller is expected to handle
    empty results, so we never raise.
    """

    source_id = "google_news"
    source_name = "Google News"

    def __init__(
        self,
        fetcher: RssFetcher | None = None,
        timeout: int = 15,
        max_items_per_symbol: int = 25,
    ) -> None:
        self.fetcher = fetcher or FeedparserRssFetcher()
        self.timeout = timeout
        self.max_items_per_symbol = max_items_per_symbol

    def fetch_ticker_news(self, symbol: str) -> list[dict[str, Any]]:
        clean_symbol = (symbol or "").strip().upper()

        if not clean_symbol:
            return []

        query = quote_plus(f"{clean_symbol} stock")
        url = (
            f"{GOOGLE_NEWS_RSS_BASE}?q={query}"
            "&hl=en-US&gl=US&ceid=US:en"
        )

        try:
            entries = self.fetcher.fetch(url=url, timeout=self.timeout)
        except Exception:
            entries = []

        if not entries:
            return []

        items: list[dict[str, Any]] = []

        for entry in entries[: self.max_items_per_symbol]:
            title = (entry.get("title") or "").strip()
            link = (entry.get("link") or "").strip()

            if not title or not link:
                continue

            items.append(
                {
                    "event_type": "NEWS",
                    "source": self.source_id,
                    "source_title": entry.get("source_title") or self.source_name,
                    "source_url": link,
                    "headline": title,
                    "raw_summary": entry.get("summary"),
                    "symbol": clean_symbol,
                    "event_time": entry.get("published"),
                    "event_metadata": {
                        "provider": self.source_id,
                        "query_symbol": clean_symbol,
                    },
                }
            )

        return items

    def fetch_market_news(self) -> list[dict[str, Any]]:
        query = quote_plus("stock market")
        url = (
            f"{GOOGLE_NEWS_RSS_BASE}?q={query}"
            "&hl=en-US&gl=US&ceid=US:en"
        )

        try:
            entries = self.fetcher.fetch(url=url, timeout=self.timeout)
        except Exception:
            entries = []

        if not entries:
            return []

        items: list[dict[str, Any]] = []

        for entry in entries[: self.max_items_per_symbol]:
            title = (entry.get("title") or "").strip()
            link = (entry.get("link") or "").strip()

            if not title or not link:
                continue

            items.append(
                {
                    "event_type": "NEWS",
                    "source": self.source_id,
                    "source_title": entry.get("source_title") or self.source_name,
                    "source_url": link,
                    "headline": title,
                    "raw_summary": entry.get("summary"),
                    "symbol": None,
                    "event_time": entry.get("published"),
                    "event_metadata": {
                        "provider": self.source_id,
                        "query_symbol": None,
                    },
                }
            )

        return items
