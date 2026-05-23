"""Phase 30 — Daily Opportunities page.

The main candidate page. Shows action labels (not just scores), instrument
scope, priority/confidence, the user-readable suggested action, action items,
the next review trigger, filters, expandable details, an option-data warning
(prompt, never a rejection), and feedback buttons. Pure display logic lives in
``app.ui_experience``; this file is loaded only by ``streamlit run``.
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
from app.dashboard.components.ui_common import view_mode_selector  # noqa: E402
from app.ui_experience.page_views import build_opportunity_row  # noqa: E402
from app.ui_experience.render_helpers import (  # noqa: E402
    format_score,
    instrument_scope_label,
)
from app.ui_experience.view_mode import is_advanced  # noqa: E402

settings = get_settings()
st.set_page_config(page_title=f"{settings.app_name} — Daily Opportunities", layout="wide")
st.title("Daily Opportunities")
st.caption(
    "Action-labeled research candidates. Missing option data shows as a "
    "prompt to paste a contract — never as a rejection."
)

view_mode = view_mode_selector()

# --- Filters ---------------------------------------------------------------

with st.expander("Filters", expanded=False):
    symbol_filter = st.text_input("Ticker").strip().upper()
    label_filter = st.text_input("Final action label contains").strip().upper()
    scope_filter = st.selectbox(
        "Instrument scope",
        ["(any)", "STOCK_ONLY", "OPTION_AVAILABLE", "OPTION_REJECTED"],
    )
    risk_only = st.checkbox("Only show items with an option-data warning")

listing = get_json("/api/action-suggestions", limit=200)
rows = listing.get("suggestions", []) if listing else []

# Apply filters client-side (deterministic).
if symbol_filter:
    rows = [r for r in rows if (r.get("symbol") or "").upper() == symbol_filter]
if label_filter:
    rows = [r for r in rows if label_filter in (r.get("final_action_label") or "").upper()]
if scope_filter != "(any)":
    rows = [r for r in rows if (r.get("instrument_scope") or "").upper() == scope_filter]

if not rows:
    st.info("No action suggestions yet. Run Recommendations or analyze a ticker.")

for suggestion in rows:
    view = build_opportunity_row(suggestion)
    if risk_only and not view["option_data_warning"]:
        continue

    header = (
        f"**{view['ticker']}** · {view['final_action_label']} · "
        f"{instrument_scope_label(view['instrument_scope'])}"
    )
    st.markdown(header)
    st.write(view["suggested_action_summary"] or "")
    cols = st.columns(3)
    cols[0].metric("Priority", format_score(view["priority_score"]))
    cols[1].metric("Confidence", format_score(view["confidence_score"]))
    cols[2].write(f"Next review: {view['next_review_trigger']}")

    if view["option_data_warning"]:
        st.warning(view["option_data_warning"])

    if view["action_items"]:
        st.caption("Action items:")
        for item in view["action_items"]:
            st.write(f"- {item.get('description', item)}")

    with st.expander("Details (checklist, trace, confidence, memory)"):
        if is_advanced(view_mode):
            st.json(suggestion)
        else:
            st.write("Switch to Advanced view to see traces and raw detail.")
            st.write({"lifecycle_state": view["lifecycle_state"]})

    # Feedback buttons (Phase 30.11) — recorded via lifecycle review state;
    # richer user-action capture arrives in Phase 38.
    fb = st.columns(4)
    sym = view["ticker"]
    if fb[0].button("Reviewed", key=f"rev_{sym}"):
        post_json(f"/api/lifecycle/{sym}/review", {"review_status": "REVIEWED"})
    if fb[1].button("Watch", key=f"watch_{sym}"):
        post_json(f"/api/lifecycle/{sym}/review", {"review_status": "REVIEWED", "notes": "watch"})
    if fb[2].button("Reject", key=f"rej_{sym}"):
        post_json(f"/api/lifecycle/{sym}/review", {"review_status": "DISMISSED"})
    if fb[3].button("Manual trade", key=f"trade_{sym}"):
        post_json("/api/user-actions", {"symbol": sym, "action_type": "MANUAL_TRADE"})
    st.divider()
