"""Phase 38 — User Override History page."""

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
st.set_page_config(page_title=f"{settings.app_name} — User Override History", layout="wide")
st.title("User Override History")
st.caption(
    "Actions you took that differed from the system suggestion. A disagreement "
    "is not assumed wrong — its outcome is classified later from real returns."
)

if st.button("Re-evaluate override outcomes"):
    result = post_json("/api/user-actions/track-outcomes", {})
    if result is not None:
        st.success(f"Evaluated: {result['result']}")

quality = get_json("/api/user-actions/decision-quality")
if quality is not None:
    st.subheader("Decision quality summary")
    st.json(quality["summary"])

st.subheader("Overrides")
overrides = get_json("/api/user-actions/overrides")
if overrides is not None and overrides.get("overrides"):
    st.dataframe(overrides["overrides"], use_container_width=True)
else:
    st.info("No overrides recorded yet.")

st.subheader("All actions")
actions = get_json("/api/user-actions")
if actions is not None and actions.get("actions"):
    st.dataframe(actions["actions"], use_container_width=True)
else:
    st.info("No user actions recorded yet.")
