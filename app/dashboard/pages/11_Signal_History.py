"""Phase 39 — Signal History page."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.dashboard.components.api_client import get_json, post_json  # noqa: E402

settings = get_settings()
st.set_page_config(page_title=f"{settings.app_name} — Signal History", layout="wide")
st.title("Signal History")
st.caption(
    "Forward outcomes of past recommendations at 5/10/20/30-day horizons. "
    "Returns are computed only when enough price history exists; option "
    "outcomes are unavailable unless real manual option data existed."
)

if st.button("Run outcome tracking (after-close job)"):
    result = post_json("/api/outcomes/signals/run", {})
    if result is not None:
        st.success(f"Tracked: {result['result']}")

symbol = st.text_input("Filter by ticker").strip().upper()
params = {"symbol": symbol} if symbol else {}
outcomes = get_json("/api/outcomes/signals", **params)
if outcomes is not None and outcomes.get("outcomes"):
    st.dataframe(outcomes["outcomes"], use_container_width=True)
else:
    st.info("No signal outcomes yet. Run outcome tracking after generating signals.")
