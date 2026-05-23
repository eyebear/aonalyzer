"""Phase 36 — News / Events page.

Full event browser over normalized events: date-window / ticker / event-type /
importance filters, source links (only when available), AI summary, price-in
assessment, similar event memory, and a persisted reviewed flag.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.dashboard.components.api_client import get_json, post_json  # noqa: E402
from app.ui_experience.event_views import (  # noqa: E402
    DATE_WINDOWS,
    build_event_row,
    filter_events,
)

settings = get_settings()
st.set_page_config(page_title=f"{settings.app_name} — News / Events", layout="wide")
st.title("News / Events")
st.caption(
    "Browse normalized events for any ticker. Pick a ticker to refresh and "
    "view its news; filters are deterministic."
)

# --- Ticker selection ------------------------------------------------------
# Watchlist tickers populate the selector; any other symbol can be typed in.
tickers_resp = get_json("/api/tickers")
watchlist_symbols = sorted(
    {
        str(t.get("symbol", "")).strip().upper()
        for t in (tickers_resp or {}).get("tickers", [])
        if t.get("symbol")
    }
)

OTHER_CHOICE = "Other…"
ALL_CHOICE = "(all tickers)"

cols = st.columns(4)
date_window = cols[0].selectbox("Window", list(DATE_WINDOWS.keys()), index=3)
ticker_choice = cols[1].selectbox(
    "Ticker", [ALL_CHOICE, *watchlist_symbols, OTHER_CHOICE]
)
event_type = cols[2].selectbox(
    "Type", ["(any)", "NEWS", "FILING", "MACRO", "EARNINGS", "OTHER"]
)
importance = cols[3].selectbox("Importance", ["(any)", "HIGH", "MEDIUM", "LOW"])

if ticker_choice == OTHER_CHOICE:
    symbol = st.text_input("Type any ticker symbol").strip().upper()
elif ticker_choice == ALL_CHOICE:
    symbol = ""
else:
    symbol = ticker_choice

# --- Per-ticker news refresh -----------------------------------------------

if symbol:
    if symbol not in watchlist_symbols:
        st.caption(
            f"{symbol} is not a watchlist ticker. News can still be fetched "
            "for it; add it to the watchlist for scheduled refreshes."
        )
    refresh_label = f"Refresh news for {symbol}"
    refresh_symbols = [symbol]
else:
    refresh_label = "Refresh news for all watchlist tickers"
    refresh_symbols = watchlist_symbols

if st.button(refresh_label, disabled=not refresh_symbols):
    refresh = post_json(
        "/api/agent/refresh/news", {"symbols": refresh_symbols}, timeout=120
    )
    if refresh is not None:
        body = refresh.get("result") or {}
        inserted = body.get("events_inserted", 0)
        duplicates = body.get("duplicate_events", 0)
        failed = body.get("failed_symbols") or []
        st.success(
            f"Fetched {inserted} new item(s) for "
            f"{', '.join(body.get('successful_symbols') or refresh_symbols)} "
            f"({duplicates} already stored)."
        )
        if failed:
            reasons = body.get("failed_reasons") or {}
            for failed_symbol in failed:
                st.warning(
                    f"News refresh failed for {failed_symbol}: "
                    f"{reasons.get(failed_symbol, 'provider error')}"
                )

# --- Event listing ---------------------------------------------------------
# Fetch a broad set and filter client-side deterministically.
listing = get_json("/api/events", limit=500, **({"symbol": symbol} if symbol else {}))
events = listing.get("events", []) if listing else []
events = filter_events(
    events,
    date_window=date_window,
    symbol=symbol or None,
    event_type=event_type,
    importance_level=importance,
)

if not events:
    if symbol:
        st.info(
            f"No stored news matches the current filters for {symbol}. "
            f"Use “Refresh news for {symbol}” above to fetch the latest items, "
            "or widen the date window."
        )
    else:
        st.info("No events match the current filters.")

for event in events:
    row = build_event_row(event)
    st.markdown(
        f"**{row['symbol'] or '—'}** · {row['event_type']} · {row['importance_level']}"
        + (" · ✅ reviewed" if row["is_reviewed"] else "")
    )
    st.write(row["headline"] or "(no headline)")
    if row["has_source_link"]:
        st.markdown(f"[Open source]({row['source_url']})")
    if row["ai_summary"]:
        st.info(f"AI summary: {row['ai_summary']}")
    if row["price_in_assessment"]:
        st.caption(f"Price-in assessment: {row['price_in_assessment']}")
    if not row["is_reviewed"]:
        if st.button("Mark reviewed", key=f"review_{row['id']}"):
            post_json(f"/api/events/{row['id']}/reviewed", {"reviewed": True})
            st.success("Marked reviewed.")
    st.divider()
