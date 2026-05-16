from __future__ import annotations

from typing import Any


class PlaceholderIvHistorySource:
    """Placeholder IV-history source.

    Real IV history requires a broker/data provider (Tradier, Polygon, ORATS,
    Tastytrade, etc.) with API keys. IV history is **optional** in Aonalyzer:
    when this source returns empty, the IV risk service must surface
    IV_DATA_NOT_AVAILABLE — never a fabricated rank/percentile.
    """

    source_id = "placeholder_iv_history"
    source_name = "Placeholder IV History"

    def fetch_ticker_iv_history(self, symbol: str) -> list[dict[str, Any]]:
        clean_symbol = (symbol or "").strip().upper()
        if not clean_symbol:
            return []
        return []
