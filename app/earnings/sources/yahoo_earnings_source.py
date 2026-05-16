from __future__ import annotations

from typing import Any


class YahooEarningsCalendarSource:
    """Placeholder Yahoo earnings calendar source.

    Real Yahoo earnings collection is intentionally not enabled yet:
    the Yahoo earnings calendar endpoint is unstable / frequently blocked,
    and locking the codebase to one provider is undesirable. This stub keeps
    the FilingService / EarningsCalendarService Protocol contract stable so
    a future replacement is a drop-in. It always returns an empty list and
    never raises.
    """

    source_id = "yahoo_earnings"
    source_name = "Yahoo Earnings"

    def fetch_ticker_earnings(self, symbol: str) -> list[dict[str, Any]]:
        clean_symbol = (symbol or "").strip().upper()

        if not clean_symbol:
            return []

        return []
