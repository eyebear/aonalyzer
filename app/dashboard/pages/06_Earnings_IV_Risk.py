"""Phase 35 — Earnings / IV Risk page.

Dedicated earnings + IV view: next earnings date, days to earnings,
earnings-before-expiration (only when an option expiration exists), IV
rank/percentile (when available), pasted option IV, an explicit IV-unavailable
state, IV crush risk (only when calculable), and refresh/filter controls.
Never shows fake IV risk when IV data is missing.
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
from app.dashboard.components.ui_common import render_kv  # noqa: E402
from app.ui_experience.risk_views import build_earnings_iv_view  # noqa: E402

settings = get_settings()
st.set_page_config(page_title=f"{settings.app_name} — Earnings / IV Risk", layout="wide")
st.title("Earnings / IV Risk")
st.caption(
    "Earnings timing and implied-volatility risk. Missing IV is shown as "
    "unavailable — never as low risk. IV crush risk appears only when both an "
    "IV reading and an earnings date exist."
)

col_refresh = st.columns(2)
if col_refresh[0].button("Refresh Earnings"):
    post_json("/api/agent/refresh/earnings")
    st.success("Earnings refresh recorded.")
if col_refresh[1].button("Refresh IV Risk"):
    post_json("/api/agent/refresh/iv-risk")
    st.success("IV risk refresh recorded.")

symbol = st.text_input("Ticker", value="AMD").strip().upper()
if not symbol:
    st.stop()

earnings_resp = get_json(f"/api/tickers/{symbol}/earnings-risk")
iv_resp = get_json(f"/api/tickers/{symbol}/iv-risk")

earnings = earnings_resp.get("snapshot") if earnings_resp else None
iv = iv_resp.get("snapshot") if iv_resp else None

# Has the user pasted an option (giving us an expiration + pasted IV)?
snaps = get_json("/api/options/manual-snapshots", symbol=symbol, limit=1)
pasted = snaps["snapshots"][0] if snaps and snaps.get("snapshots") else None
option_expiration_present = bool(pasted and pasted.get("expiration_date"))
pasted_iv = pasted.get("implied_volatility") if pasted else None

view = build_earnings_iv_view(
    earnings=earnings,
    iv=iv,
    option_expiration_present=option_expiration_present,
    pasted_option_iv=pasted_iv,
)

st.subheader("Earnings")
render_kv(view["earnings"])

st.subheader("Implied Volatility")
if not view["iv"].get("available"):
    st.warning(view["iv"].get("detail") or "IV data is not available.")
render_kv(view["iv"], skip=("detail",))

st.subheader("IV Crush Risk")
crush = view["iv_crush_risk"]
if not crush["calculable"]:
    st.info(crush["detail"])
else:
    st.write(f"Level: **{crush['level']}** — {crush['detail']}")

st.subheader("Similar high-IV failure memory")
cases = get_json("/api/memory/cases", symbol=symbol, limit=5)
if cases is not None and cases.get("cases"):
    st.dataframe(cases["cases"], use_container_width=True)
else:
    st.caption("No similar high-IV failure cases stored yet.")
