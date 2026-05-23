"""Phase 31 — Rejected But Interesting page.

Shows rejected / partially-rejected opportunities: the stock thesis (why it
may still be interesting), option failures ONLY when option data actually
existed, the main rejection reason, suggested watch condition, next review
trigger, rejected manual option snapshots, similar rejection memory, and
filters. Missing option data never places a candidate here by itself.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.dashboard.components.api_client import get_json  # noqa: E402
from app.dashboard.components.ui_common import view_mode_selector  # noqa: E402
from app.ui_experience.page_views import build_rejected_row  # noqa: E402
from app.ui_experience.view_mode import is_advanced  # noqa: E402

settings = get_settings()
st.set_page_config(
    page_title=f"{settings.app_name} — Rejected But Interesting", layout="wide"
)
st.title("Rejected But Interesting")
st.caption(
    "Candidates the system rejected or partially rejected but that may still "
    "be worth watching. Option failures appear only when option data was "
    "actually pasted and evaluated."
)

view_mode = view_mode_selector()

with st.expander("Filters", expanded=False):
    symbol_filter = st.text_input("Ticker").strip().upper()
    only_interesting = st.checkbox("Only rejected-but-interesting", value=True)
    show_option_failures_only = st.checkbox("Only show contract-level option failures")

path = "/api/rejections/interesting" if only_interesting else "/api/rejections"
listing = get_json(path, limit=200)
rows = (
    listing.get("candidates", listing.get("rejections", []))
    if listing
    else []
)

if symbol_filter:
    rows = [r for r in rows if (r.get("symbol") or "").upper() == symbol_filter]

if not rows:
    st.info("No rejected-but-interesting candidates right now.")

for candidate in rows:
    view = build_rejected_row(candidate)
    if show_option_failures_only and not view["show_option_failure"]:
        continue

    st.markdown(
        f"**{view['ticker']}** · {view['rejection_category']} "
        f"({view['rejection_severity']})"
    )
    st.write(f"Main reason: {view['main_rejection_reason']}")
    if view["interesting_reasons"]:
        st.caption("Still interesting because: " + ", ".join(view["interesting_reasons"]))

    if view["show_option_failure"]:
        st.warning("Option contract failures (option data was evaluated):")
        for failure in view["option_failures"]:
            st.write(f"- {failure['reason_label']}: {failure['explanation']}")
    else:
        st.caption(
            "No contract-level option failure shown — either no option data was "
            "pasted, or the rejection is stock-side only."
        )

    # Similar rejection memory (Phase 41+ populates; degrades gracefully).
    mem = get_json("/api/memory/cases", symbol=view["ticker"], limit=3)
    if mem is not None and mem.get("cases"):
        st.caption(f"Similar past rejections: {len(mem['cases'])} on file.")

    with st.expander("Details"):
        if is_advanced(view_mode):
            st.json(candidate)
        else:
            st.write({"stock_reasons": view["stock_reasons"], "summary": view["summary"]})
    st.divider()
