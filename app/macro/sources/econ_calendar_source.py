from __future__ import annotations

from typing import Any


class EconCalendarSource:
    """Placeholder macroeconomic calendar source.

    Real macro collection (FRED, BoC, ECB, BoJ, Investing.com) requires
    provider-specific clients and in some cases API keys. This stub keeps
    the interface stable and fails safely, never raising.
    """

    source_id = "econ_calendar"
    source_name = "Economic Calendar"

    def fetch_macro_events(self) -> list[dict[str, Any]]:
        return []
