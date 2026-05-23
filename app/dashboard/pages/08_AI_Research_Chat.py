"""Phase 37 — AI Research Chat page (+ floating-style entry).

Full chat page with answer-mode selection. The assistant uses only system
context, never invents missing option values, and never overrides hard
filters. When no AI provider is configured it returns a deterministic
degraded-state answer.
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

settings = get_settings()
st.set_page_config(page_title=f"{settings.app_name} — AI Research Chat", layout="wide")
st.title("AI Research Chat")
st.caption(
    "Ask about a ticker's decision, risks, or pasted option data. Answers use "
    "only the system's context, never invent missing option values, and never "
    "override hard filters. Research support only — not financial advice."
)

modes_resp = get_json("/api/chat/modes")
modes = modes_resp.get("modes", ["EXPLAIN"]) if modes_resp else ["EXPLAIN"]

col = st.columns([1, 1])
symbol = col[0].text_input("Ticker", value="AMD").strip().upper()
mode = col[1].selectbox("Answer mode", modes)
question = st.text_area("Your question", value=f"Explain the setup for {symbol}.")
snapshot_id = st.session_state.get("manual_snapshot_id")

if st.button("Ask"):
    body = {"symbol": symbol, "mode": mode, "question": question}
    if snapshot_id:
        body["manual_option_snapshot_id"] = snapshot_id
        body["option_data_requested"] = True
    result = post_json("/api/chat", body)
    if result is not None:
        resp = result["response"]
        if resp["degraded"]:
            st.info(f"Degraded mode ({resp['provider_status']}) — deterministic answer.")
        st.markdown(resp["answer"])
        st.caption(f"Option data status: {resp['option_data_status']}")
        with st.expander("Sources & citations"):
            st.json({"sources": resp["sources"], "citations": resp["citations"]})
        with st.expander("Context summary"):
            st.json(resp["context_summary"])
