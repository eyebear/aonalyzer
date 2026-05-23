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
from app.ui_experience.render_helpers import (  # noqa: E402
    action_label_display,
    action_label_next_step,
)

settings = get_settings()
st.set_page_config(page_title=f"{settings.app_name} — Signal History", layout="wide")
st.title("Signal History")
st.caption(
    "Forward outcomes of past recommendations at 5/10/20/30-day horizons. "
    "Returns are computed only when enough price history exists; option "
    "outcomes are unavailable unless real manual option data existed."
)
st.warning(
    "Option outcomes marked ESTIMATED are a delta-approximation **proxy** of "
    "the stock move — not market-priced option P&L. They ignore theta decay, "
    "gamma, and IV change."
)

if st.button("Run outcome tracking (after-close job)"):
    result = post_json("/api/outcomes/signals/run", {})
    if result is not None:
        st.success(f"Tracked: {result.get('result')}")

symbol = st.text_input("Filter by ticker").strip().upper()
params = {"symbol": symbol} if symbol else {}
outcomes = get_json("/api/outcomes/signals", **params)
rows = (outcomes or {}).get("outcomes") or []
if rows:
    st.dataframe(
        [
            {
                "Symbol": row.get("symbol"),
                "Signal date": row.get("signal_date"),
                "Horizon (days)": row.get("horizon_days"),
                "Final action": action_label_display(row.get("final_action_label")),
                "Stock return %": row.get("stock_return_pct"),
                "Target hit": row.get("target_hit"),
                "Stop hit": row.get("stop_hit"),
                "Option outcome": row.get("option_outcome_status"),
            }
            for row in rows
        ],
        use_container_width=True,
        hide_index=True,
    )

    # Diagnostic labels (e.g. insufficient price history) are explained with a
    # concrete next step instead of being left as raw status codes.
    next_steps: dict[str, list[str]] = {}
    for row in rows:
        guidance = action_label_next_step(row.get("final_action_label"))
        if guidance:
            next_steps.setdefault(guidance, []).append(str(row.get("symbol") or "?"))
    for guidance, symbols in next_steps.items():
        affected = ", ".join(sorted(set(symbols)))
        st.info(f"{affected}: {guidance}")

    with st.expander("Raw outcome rows (advanced)", expanded=False):
        st.dataframe(rows, use_container_width=True)
else:
    st.info("No signal outcomes yet. Run outcome tracking after generating signals.")
