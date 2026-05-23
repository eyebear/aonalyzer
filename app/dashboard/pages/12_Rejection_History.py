"""Phase 40 — Rejection History page (rejections + do-not-touch outcomes)."""

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
st.set_page_config(page_title=f"{settings.app_name} — Rejection History", layout="wide")
st.title("Rejection History")
st.caption(
    "Did past rejections and freezes turn out useful? Option outcomes are shown "
    "as unavailable unless real manual option data existed — never backfilled."
)

if st.button("Run rejection / freeze outcome tracking"):
    result = post_json("/api/outcomes/rejections/run", {})
    if result is not None:
        st.success(f"Tracked: {result['result']}")

source = st.selectbox("Source", ["(any)", "REJECTION", "DO_NOT_TOUCH"])
symbol = st.text_input("Filter by ticker").strip().upper()
params: dict = {}
if symbol:
    params["symbol"] = symbol
if source != "(any)":
    params["source_type"] = source
outcomes = get_json("/api/outcomes/rejections", **params)
if outcomes is not None and outcomes.get("outcomes"):
    st.dataframe(outcomes["outcomes"], use_container_width=True)
else:
    st.info("No rejection/freeze outcomes yet.")
