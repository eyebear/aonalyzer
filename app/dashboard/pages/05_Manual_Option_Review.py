"""Phase 34 — Manual Option Review page (formerly "Option Candidates").

Focuses on manually-pasted option snapshots: symbol / DTE / premium / call-put
filters, liquidity, IV & Greeks, breakeven, target-vs-breakeven, parser
confidence, missing fields, AI explanation, suitability/rejection, and
re-parse / re-analyze controls. Never implies a live broker option-chain feed.
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
from app.dashboard.components.ui_common import (  # noqa: E402
    manual_option_shortcut,
    view_mode_selector,
)
from app.ui_experience.option_views import (  # noqa: E402
    MANUAL_OPTION_EMPTY_STATE,
    build_manual_option_review_row,
)
from app.ui_experience.view_mode import is_advanced  # noqa: E402

settings = get_settings()
st.set_page_config(page_title=f"{settings.app_name} — Manual Option Review", layout="wide")
st.title("Manual Option Review")
st.caption(
    "Review option contracts you have pasted manually. DTE, premium, liquidity, "
    "IV, Greeks, and breakeven appear only when available or calculable."
)

view_mode = view_mode_selector()

# --- Filters ---------------------------------------------------------------

with st.expander("Filters", expanded=False):
    symbol_filter = st.text_input("Symbol").strip().upper()
    type_filter = st.selectbox("Call/Put", ["(any)", "CALL", "PUT"])
    dte_max = st.number_input("Max DTE (0 = no limit)", min_value=0, value=0)
    premium_max = st.number_input("Max premium (0 = no limit)", min_value=0.0, value=0.0)

params: dict = {"limit": 200}
if symbol_filter:
    params["symbol"] = symbol_filter
listing = get_json("/api/options/manual-snapshots", **params)
snapshots = listing.get("snapshots", []) if listing else []

# Deterministic client-side filtering.
def _keep(s: dict) -> bool:
    if type_filter != "(any)" and (s.get("option_type") or "").upper() != type_filter:
        return False
    if dte_max and s.get("dte") is not None and s["dte"] > dte_max:
        return False
    if premium_max:
        prem = s.get("last_price") or s.get("mid_price")
        if prem is not None and prem > premium_max:
            return False
    return True


snapshots = [s for s in snapshots if _keep(s)]

if not snapshots:
    st.info(MANUAL_OPTION_EMPTY_STATE)

for snapshot in snapshots:
    sid = snapshot.get("id")
    candidate = get_json("/api/option-suitability/candidates/latest", manual_option_snapshot_id=sid)
    cand = candidate.get("candidate") if candidate else None
    row = build_manual_option_review_row(snapshot, cand)

    st.markdown(
        f"**{row['symbol']} {row['option_type']} {row['strike']}** "
        f"(exp {row['expiration_date']}, DTE {row['dte']})"
    )
    cols = st.columns(4)
    cols[0].write(f"Premium: {row['premium']}")
    cols[1].write(f"Breakeven: {row['breakeven']}")
    cols[2].write(f"IV: {row['implied_volatility']}")
    cols[3].write(f"Parser: {row['parser_confidence']}")

    if row["missing_fields"]:
        st.caption(f"Missing fields (not invented): {', '.join(row['missing_fields'])}")
    if row["ai_summary"]:
        st.info(f"AI: {row['ai_summary']}")
    if row["suitability_status"]:
        st.write(f"Suitability: {row['suitability_status']}")
    if row["rejection_reasons"]:
        st.warning("Failed checks: " + ", ".join(map(str, row["rejection_reasons"])))

    rc = st.columns(2)
    if rc[0].button("Re-analyze (AI)", key=f"reanalyze_{sid}"):
        post_json(f"/api/options/manual-snapshots/{sid}/analyze")
        st.success("Re-analyzed.")
    if rc[1].button("Re-evaluate suitability", key=f"reeval_{sid}"):
        post_json(f"/api/option-suitability/snapshots/{sid}/evaluate")
        st.success("Re-evaluated.")

    if is_advanced(view_mode):
        with st.expander("Raw snapshot"):
            st.json(snapshot)
    st.divider()

st.subheader("Paste a new option contract")
manual_option_shortcut(key_prefix="mor_manual_opt")
