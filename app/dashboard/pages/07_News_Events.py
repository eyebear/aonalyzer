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
st.caption("Browse normalized events. Filters are deterministic; nothing is re-ingested here.")

cols = st.columns(4)
date_window = cols[0].selectbox("Window", list(DATE_WINDOWS.keys()), index=3)
symbol = cols[1].text_input("Ticker").strip().upper()
event_type = cols[2].selectbox(
    "Type", ["(any)", "NEWS", "FILING", "MACRO", "EARNINGS", "OTHER"]
)
importance = cols[3].selectbox("Importance", ["(any)", "HIGH", "MEDIUM", "LOW"])

# Fetch a broad set and filter client-side deterministically.
listing = get_json("/api/events", limit=500)
events = listing.get("events", []) if listing else []
events = filter_events(
    events,
    date_window=date_window,
    symbol=symbol or None,
    event_type=event_type,
    importance_level=importance,
)

if not events:
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
