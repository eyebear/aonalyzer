from __future__ import annotations

from typing import Any


class SecEdgarFilingSource:
    """Placeholder SEC EDGAR source.

    Real EDGAR collection requires submitting a User-Agent string with a
    contact email and respecting their rate limits. This placeholder keeps
    the interface stable so a future replacement can swap in without
    changing the FilingService. It always returns an empty list, fails
    safely, and never raises.
    """

    source_id = "sec_edgar"
    source_name = "SEC EDGAR"

    def fetch_ticker_filings(self, symbol: str) -> list[dict[str, Any]]:
        clean_symbol = (symbol or "").strip().upper()

        if not clean_symbol:
            return []

        return []
