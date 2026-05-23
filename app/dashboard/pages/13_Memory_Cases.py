"""Phase 41 — Memory Cases page."""

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
st.set_page_config(page_title=f"{settings.app_name} — Memory Cases", layout="wide")
st.title("Memory Cases")
st.caption(
    "Reusable lessons built from real outcomes. Includes the key "
    "stock-right/option-wrong and stock-right/option-missing patterns."
)

if st.button("Build cases from outcomes"):
    result = post_json("/api/memory/cases/build", {})
    if result is not None:
        st.success(f"Cases: {result['result']}")

cols = st.columns(2)
symbol = cols[0].text_input("Filter by ticker").strip().upper()
case_type = cols[1].selectbox(
    "Case type",
    [
        "(any)",
        "STOCK_RIGHT_OPTION_WRONG",
        "STOCK_RIGHT_OPTION_MISSING",
        "MANUAL_OPTION_ANALYSIS",
        "SIGNAL_OUTCOME",
        "REJECTION_OUTCOME",
        "OVERRIDE",
        "DO_NOT_TOUCH",
    ],
)

params: dict = {}
if symbol:
    params["symbol"] = symbol
if case_type != "(any)":
    params["case_type"] = case_type

cases = get_json("/api/memory/cases", **params)
if cases is not None and cases.get("cases"):
    st.dataframe(cases["cases"], use_container_width=True)
else:
    st.info("No memory cases yet. Run outcome tracking, then build cases.")

st.subheader("Search similar memory (vector)")
query = st.text_input("Search query")
if st.button("Search") and query:
    result = post_json("/api/memory/vector/search", {"query_text": query, "limit": 10})
    if result is not None:
        st.dataframe(result["results"], use_container_width=True)
