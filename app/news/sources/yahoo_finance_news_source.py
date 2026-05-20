from __future__ import annotations

from typing import Any

from app.news.sources.rss_fetcher import FeedparserRssFetcher, RssFetcher

YAHOO_FINANCE_RSS_TEMPLATE = (
    "https://feeds.finance.yahoo.com/rss/2.0/headline"
    "?s={symbol}&region=US&lang=en-US"
)


class YahooFinanceNewsSource:
    """Yahoo Finance ticker-tagged RSS source.

    Fails safely when the feed is blocked, slow, malformed, or empty.
    """

    source_id = "yahoo_finance_news"
    source_name = "Yahoo Finance"

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

        url = YAHOO_FINANCE_RSS_TEMPLATE.format(symbol=clean_symbol)

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
