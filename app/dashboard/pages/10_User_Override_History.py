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
        st.success(f"Evaluated: {result.get('result')}")

quality = get_json("/api/user-actions/decision-quality")
summary = (quality or {}).get("summary") or {}
if summary:
    st.subheader("Decision quality summary")
    top = st.columns(4)
    top[0].metric("Total actions", summary.get("total_actions", 0))
    top[1].metric("Overrides", summary.get("total_overrides", 0))
    top[2].metric("You were right", summary.get("user_right", 0))
    top[3].metric("System was right", summary.get("system_right", 0))
    st.dataframe(
        [
            {"Measure": "Manual trades", "Count": summary.get("manual_trades", 0)},
            {
                "Measure": "Manual option actions",
                "Count": summary.get("manual_option_actions", 0),
            },
            {
                "Measure": "Traded against a rejection",
                "Count": summary.get("overrides_traded_against_rejection", 0),
            },
            {
                "Measure": "Ignored a recommendation",
                "Count": summary.get("overrides_ignored_recommendation", 0),
            },
            {
                "Measure": "Missed opportunities",
                "Count": summary.get("missed_opportunities", 0),
            },
            {
                "Measure": "Avoided correctly",
                "Count": summary.get("avoided_correctly", 0),
            },
            {"Measure": "Neutral", "Count": summary.get("neutral", 0)},
            {"Measure": "Pending evaluation", "Count": summary.get("pending", 0)},
        ],
        use_container_width=True,
        hide_index=True,
    )
    with st.expander("Raw diagnostics", expanded=False):
        st.json(summary)

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
