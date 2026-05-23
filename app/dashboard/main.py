"""Phase 29 — Home command center (Streamlit entry point).

Worklist-first Home page with progressive disclosure: Today's Research
Worklist, Agent Status, manual refresh, manual option shortcut, major risk
alerts, market regime, recent events, and memory warnings. Beginner mode keeps
it lean; advanced mode reveals raw detail. Pure logic lives in
``app.ui_experience``; this file is loaded only by ``streamlit run``.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.dashboard.components.api_client import get_json, post_json  # noqa: E402
from app.dashboard.components.ui_common import (  # noqa: E402
    manual_option_shortcut,
    view_mode_selector,
)
from app.ui_experience.render_helpers import (  # noqa: E402
    priority_badge,
    sort_worklist_items,
    summarize_worklist,
)
from app.ui_experience.view_mode import is_advanced  # noqa: E402

settings = get_settings()

st.set_page_config(page_title=f"{settings.app_name} — Home", layout="wide")

st.title(settings.app_name)
st.caption(
    "Local equity & options research command center. Research and "
    "decision-support only — not auto-trading, not broker-connected."
)

# --- Sidebar: view mode + system status ------------------------------------

view_mode = view_mode_selector()
st.sidebar.caption("Missing option data never blocks stock-only research.")

with st.sidebar:
    st.subheader("Service status")
    health = get_json("/health", timeout=5)
    if health is not None:
        st.success("FastAPI reachable")
        if is_advanced(view_mode):
            st.json(health)

# --- 1) Today's Research Worklist (FIRST) ----------------------------------

st.header("Today's Research Worklist")
st.caption("Your prioritized daily research tasks, assembled from existing analysis.")

col_gen, _ = st.columns([1, 3])
with col_gen:
    if st.button("Generate / refresh worklist"):
        result = post_json("/api/worklist/generate", {})
        if result is not None:
            body = result["result"]
            st.success(
                f"Created {body['items_created']}, refreshed "
                f"{body['items_refreshed']}, removed {body['items_removed']}."
            )

worklist = get_json("/api/worklist", status="OPEN")
if worklist is not None:
    items = worklist.get("items", [])
    if not items:
        st.info("No open worklist items. Generate the worklist or run an analysis.")
    else:
        summary = summarize_worklist(items)
        st.write(" · ".join(f"{k}: {v}" for k, v in summary.items()))
        for item in sort_worklist_items(items):
            with st.container():
                st.markdown(
                    f"**{priority_badge(item['priority'])} · {item['symbol']}** "
                    f"— {item['worklist_type']}"
                )
                st.write(item["summary"])
                if is_advanced(view_mode):
                    with st.expander("Details", expanded=False):
                        st.json(item)

st.divider()

# --- 2) Agent Status Panel -------------------------------------------------

st.header("Agent Status")
agent_status = get_json("/api/agent/status", timeout=5)
if agent_status is not None:
    st.json(agent_status) if is_advanced(view_mode) else st.write(
        f"Scheduler running: {agent_status.get('scheduler_running', 'unknown')}"
    )
runs = get_json("/api/agent/runs", timeout=5)
if runs is not None and runs.get("runs"):
    st.dataframe(runs["runs"], use_container_width=True)

# --- 3) Manual refresh buttons ---------------------------------------------

st.header("Manual Refresh")
refresh_buttons = [
    ("Refresh All", "/api/agent/refresh/all"),
    ("Refresh Market Data", "/api/agent/refresh/market-data"),
    ("Refresh News", "/api/agent/refresh/news"),
    ("Refresh Earnings", "/api/agent/refresh/earnings"),
    ("Refresh IV Risk", "/api/agent/refresh/iv-risk"),
    ("Run Recommendations", "/api/agent/run/recommendations"),
]
cols = st.columns(3)
for index, (label, endpoint) in enumerate(refresh_buttons):
    with cols[index % 3]:
        if st.button(label):
            result = post_json(endpoint)
            if result is not None:
                st.success(f"{label} recorded.")

# --- 4) Manual option input shortcut ---------------------------------------

st.header("Paste / Analyze Option Data")
manual_option_shortcut(key_prefix="home_manual_opt")

st.divider()

# --- 5) Major risk alerts --------------------------------------------------

st.header("Major Risk Alerts")
dnt = get_json("/api/do-not-touch")
if dnt is not None:
    frozen = dnt.get("items", [])
    if frozen:
        st.warning(f"{len(frozen)} symbol(s) frozen (Do-Not-Touch).")
        st.dataframe(
            [
                {
                    "Symbol": i["symbol"],
                    "Category": i["freeze_category"],
                    "Severity": i["freeze_severity"],
                    "Expires": i["expires_at"] or "—",
                }
                for i in frozen
            ],
            use_container_width=True,
        )
    else:
        st.success("No active freezes.")

dq = get_json("/api/data-quality/status", timeout=8)
if dq is not None and dq.get("open_insufficient_data_events"):
    st.caption("Open data-quality issues:")
    st.dataframe(dq["open_insufficient_data_events"], use_container_width=True)

# --- 6) Market regime ------------------------------------------------------

st.header("Market Regime")
regime = get_json("/api/market-regime/latest", timeout=8)
if regime is not None:
    snapshot = regime.get("snapshot") or regime
    st.write(
        f"Regime: **{snapshot.get('regime_label', 'unknown')}** "
        f"(score {snapshot.get('regime_score', '—')})"
    )
    if is_advanced(view_mode):
        st.json(regime)

# --- 7) Recent important events --------------------------------------------

st.header("Recent Important Events")
events = get_json("/api/events", importance_level="HIGH", limit=20)
if events is not None and events.get("events"):
    st.dataframe(
        [
            {
                "Symbol": e.get("symbol"),
                "Type": e.get("event_type"),
                "Importance": e.get("importance_level"),
                "Headline": e.get("headline"),
            }
            for e in events["events"]
        ],
        use_container_width=True,
    )
else:
    st.info("No high-importance events recorded.")

# --- 8) Memory warning panel -----------------------------------------------

st.header("Experience Warnings")
mem_items = get_json("/api/worklist", status="OPEN", worklist_type="EXPERIENCE_WARNING")
if mem_items is not None and mem_items.get("items"):
    for item in mem_items["items"]:
        st.warning(f"{item['symbol']}: {item['summary']}")
else:
    st.caption("No experience-based warnings right now.")
