"""Phase 33 — Ticker Analyzer + Manual Option Input integration.

Manual ticker workflow: refresh price/news, re-analyze, the one-page brief,
the action panel, the manual option input flow (expected-data helper, parse,
AI explanation), parsed fields with honest missing values, option
suitability / rejected contracts (only when enough data exists), earnings/IV
risk, decision trace, confidence breakdown, memory, and user-action buttons.

Buttons: Refresh This Ticker, Refresh This Ticker News, Paste / Analyze Option
Data, Re-analyze This Ticker, Ask AI About This Ticker.
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
from app.dashboard.components.ui_common import render_kv, view_mode_selector  # noqa: E402
from app.ui_experience.view_mode import is_advanced  # noqa: E402

settings = get_settings()
st.set_page_config(page_title=f"{settings.app_name} — Ticker Analyzer", layout="wide")
st.title("Ticker Analyzer")
st.caption(
    "Look up any ticker, refresh its data, re-analyze it, and optionally paste "
    "manual option data. Stock-only analysis always works; the option side is "
    "added only when you paste a contract. No live broker option-chain feed."
)

view_mode = view_mode_selector()

symbol = st.text_input("Ticker", value="AMD").strip().upper()
if not symbol:
    st.stop()

# --- Ticker action buttons (Phase 33.2 / 33.3 / 33.9 / 33.17) --------------

b = st.columns(5)
if b[0].button("Refresh This Ticker"):
    post_json(f"/api/tickers/{symbol}/refresh/market-data")
    st.success("Market-data refresh recorded.")
if b[1].button("Refresh This Ticker News"):
    post_json(f"/api/tickers/{symbol}/refresh/news")
    st.success("News refresh recorded.")
if b[2].button("Re-analyze This Ticker"):
    post_json(f"/api/tickers/{symbol}/analyze")
    st.success("Re-analysis recorded.")
if b[3].button("Ask AI About This Ticker"):
    chat = post_json(
        "/api/chat",
        {"symbol": symbol, "mode": "EXPLAIN", "question": f"Explain the setup for {symbol}."},
    )
    if chat is not None:
        st.session_state["ticker_chat"] = chat
if b[4].button("Clear option session"):
    st.session_state.pop("manual_snapshot_id", None)

if st.session_state.get("ticker_chat"):
    with st.expander("AI answer", expanded=True):
        st.json(st.session_state["ticker_chat"])

# --- One-Page Ticker Brief (Phase 33.4) ------------------------------------

snapshot_id = st.session_state.get("manual_snapshot_id")
brief = get_json(
    f"/api/ticker-brief/{symbol}",
    **({"manual_option_snapshot_id": snapshot_id} if snapshot_id else {}),
)
if brief is not None and brief.get("brief"):
    st.subheader("One-Page Brief")
    for section in brief["brief"].get("sections") or []:
        name = section.get("section", "").replace("_", " ").title()
        with st.expander(name, expanded=section.get("section") == "current_action"):
            if not section.get("available", True) and section.get("detail"):
                st.info(section["detail"])
            else:
                render_kv(section, skip=("section", "available"))
            # Expanders cannot be nested; show the raw payload inline in
            # advanced mode only.
            if is_advanced(view_mode):
                st.caption("Raw section data (advanced)")
                st.json(section, expanded=False)

# --- Action panel (Phase 33.5) ---------------------------------------------

action = get_json(
    f"/api/action-suggestions/{symbol}",
    **(
        {"manual_option_snapshot_id": snapshot_id, "option_data_requested": True}
        if snapshot_id
        else {}
    ),
)
if action is not None and action.get("package"):
    pkg = action["package"]
    st.subheader("Action Suggestion")
    st.write(
        f"**{pkg.get('final_action_label', '—')}** — "
        f"{pkg.get('suggested_action_summary', '')}"
    )

# --- Manual option input panel (Phase 33.6 - 33.12) ------------------------

st.subheader("Manual Option Input")
st.caption(
    "Expected fields to copy & paste: symbol, expiration, strike, call/put, "
    "bid, ask, last, implied_volatility, delta, gamma, theta, vega, volume, "
    "open_interest. Missing fields are shown honestly and never invented. "
    "Option suitability runs only when enough fields exist."
)
raw_text = st.text_area("Paste option text", height=140, key="ticker_opt_text")
oc = st.columns(2)
if oc[0].button("Parse Option Text"):
    if raw_text.strip():
        result = post_json(f"/api/tickers/{symbol}/options/manual-input", {"raw_text": raw_text})
        if result is not None:
            snapshot = result.get("snapshot") or {}
            sid = snapshot.get("id")
            if sid is not None:
                st.session_state["manual_snapshot_id"] = sid
                st.success(f"Parsed and stored snapshot #{sid}.")
            else:
                st.warning("The parser did not return a stored snapshot.")
            if snapshot:
                st.json(snapshot, expanded=False)
    else:
        st.warning("Paste option text first.")

if oc[1].button("Analyze Option Text with AI"):
    sid = st.session_state.get("manual_snapshot_id")
    if sid:
        analyzed = post_json(f"/api/options/manual-snapshots/{sid}/analyze")
        if analyzed is not None:
            st.success("AI explanation generated (no values invented).")
            st.json(analyzed.get("snapshot") or analyzed, expanded=False)
    else:
        st.warning("Parse a contract first.")

# Parsed fields + suitability (Phase 33.10 - 33.12)
sid = st.session_state.get("manual_snapshot_id")
if sid:
    suitability = post_json(f"/api/option-suitability/snapshots/{sid}/evaluate")
    if suitability is not None:
        st.subheader("Option Suitability")
        if is_advanced(view_mode):
            st.json(suitability)
        else:
            st.write(suitability.get("candidate", suitability))

# --- Earnings / IV risk (Phase 33.13) --------------------------------------

st.subheader("Earnings / IV Risk")
earnings = get_json(f"/api/tickers/{symbol}/earnings-risk")
iv = get_json(f"/api/tickers/{symbol}/iv-risk")
cols = st.columns(2)
with cols[0]:
    st.caption("Earnings")
    snap = (earnings or {}).get("snapshot") or {}
    if snap:
        st.metric("Risk", str(snap.get("risk_label", "—")))
        st.metric("Days to earnings", str(snap.get("days_to_earnings") or "—"))
        if snap.get("risk_reason"):
            st.caption(snap["risk_reason"])
        if is_advanced(view_mode):
            st.json(snap, expanded=False)
    else:
        st.info("No earnings risk snapshot available.")
with cols[1]:
    st.caption("IV")
    snap = (iv or {}).get("snapshot") or {}
    if snap:
        st.metric("Risk", str(snap.get("risk_label", "—")))
        st.metric("IV rank", str(snap.get("iv_rank") if snap.get("iv_rank") is not None else "—"))
        if snap.get("risk_reason"):
            st.caption(snap["risk_reason"])
        if is_advanced(view_mode):
            st.json(snap, expanded=False)
    else:
        st.info("No IV risk snapshot available.")

# --- Memory / similar cases (Phase 33.16) ----------------------------------

st.subheader("Memory / Similar Cases")
cases = get_json("/api/memory/cases", symbol=symbol, limit=5)
if cases is not None and cases.get("cases"):
    st.dataframe(cases["cases"], use_container_width=True)
else:
    st.caption("No similar historical cases stored for this symbol yet.")
