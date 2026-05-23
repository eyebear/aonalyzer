"""Phase 25, step 25.11 — Opportunity lifecycle dashboard page.

Streamlit page that lists the current opportunity lifecycles and shows
a per-symbol transition timeline. Loaded only by ``streamlit run``;
not imported by the FastAPI app or pytest.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import requests  # noqa: E402
import streamlit as st  # noqa: E402

from app.core.config import get_settings  # noqa: E402

settings = get_settings()

st.set_page_config(
    page_title=f"{settings.app_name} — Lifecycle", layout="wide"
)
st.title("Opportunity Lifecycle")
st.caption(
    "Persistent state for every tracked opportunity, with the user-review "
    "flag and the per-symbol transition timeline."
)


def _get(path: str, **params) -> dict | None:
    url = f"{settings.api_base_url}{path}"
    try:
        response = requests.get(url, params=params, timeout=15)
    except requests.RequestException as exc:
        st.warning(f"Failed to call {path}: {exc}")
        return None
    if response.status_code != 200:
        st.warning(f"{path} returned status {response.status_code}.")
        return None
    return response.json()


def _post(path: str, body: dict | None = None) -> dict | None:
    url = f"{settings.api_base_url}{path}"
    try:
        response = requests.post(url, json=body or {}, timeout=15)
    except requests.RequestException as exc:
        st.warning(f"Failed to call {path}: {exc}")
        return None
    if response.status_code != 200:
        st.warning(f"{path} returned status {response.status_code}.")
        return None
    return response.json()


# --- Current lifecycles ---------------------------------------------------

st.subheader("Tracked symbols")

state_filter = st.selectbox(
    "State filter",
    options=[
        "(any)",
        "READY_FOR_RESEARCH",
        "WATCHING",
        "WAITING_FOR_ENTRY",
        "WAIT_FOR_MANUAL_OPTION_INPUT",
        "REJECTED",
        "INSUFFICIENT_DATA",
    ],
)
params = {} if state_filter == "(any)" else {"state": state_filter}
listing = _get("/api/lifecycle", **params)

if listing is not None:
    rows = listing.get("lifecycles", [])
    if not rows:
        st.info("No lifecycles match the current filter.")
    else:
        st.dataframe(
            [
                {
                    "Symbol": row["symbol"],
                    "State": row["current_state"],
                    "Previous": row["previous_state"] or "—",
                    "Action label": row["final_action_label"] or "—",
                    "User review": row["user_review_status"],
                    "Last transition": row["last_transition_at"],
                    "Last reactivation": row["last_reactivation_at"] or "—",
                }
                for row in rows
            ],
            use_container_width=True,
        )

st.divider()

# --- Per-symbol inspector + actions ---------------------------------------

st.subheader("Inspect a symbol")
symbol = st.text_input("Symbol", value="AMD").strip().upper()
col_eval, col_review, col_dismiss = st.columns(3)

with col_eval:
    if st.button("Re-evaluate lifecycle"):
        if symbol:
            res = _get(f"/api/lifecycle/{symbol}", evaluate="true")
            if res is not None:
                lc = res.get("lifecycle") or {}
                st.success(
                    f"{symbol}: state {lc.get('current_state', '—')} "
                    f"(was {lc.get('previous_state') or '—'}), "
                    f"review status {lc.get('user_review_status', '—')}."
                )
                with st.expander("Raw diagnostics", expanded=False):
                    st.json(res)

with col_review:
    if st.button("Mark REVIEWED"):
        if symbol:
            res = _post(
                f"/api/lifecycle/{symbol}/review",
                {"review_status": "REVIEWED"},
            )
            if res is not None:
                st.success(f"Marked {symbol} REVIEWED.")

with col_dismiss:
    if st.button("Mark DISMISSED"):
        if symbol:
            res = _post(
                f"/api/lifecycle/{symbol}/review",
                {"review_status": "DISMISSED"},
            )
            if res is not None:
                st.success(f"Marked {symbol} DISMISSED.")

# --- Transition timeline --------------------------------------------------

st.subheader("Transition timeline")
if symbol:
    history = _get(f"/api/lifecycle/history/{symbol}")
    if history is not None and history.get("history"):
        st.dataframe(
            [
                {
                    "Created": row["created_at"],
                    "From": row["from_state"] or "—",
                    "To": row["to_state"],
                    "Reason": row["transition_reason_label"],
                    "Summary": row["transition_reason_summary"],
                    "Triggered by": row["triggered_by"],
                    "Source": row["source_phase"],
                }
                for row in history["history"]
            ],
            use_container_width=True,
        )
    else:
        st.info(f"No transitions recorded for {symbol}.")

# --- Update job + reactivation -------------------------------------------

st.subheader("Maintenance")

job_cols = st.columns(2)
with job_cols[0]:
    if st.button("Run lifecycle update job now"):
        res = _post("/api/lifecycle/update", {})
        if res is not None:
            st.success(
                f"Processed {res['result']['symbols_processed']} symbols, "
                f"recorded {res['result']['transitions_recorded']} transitions, "
                f"detected {res['result']['reactivations']} reactivations."
            )
with job_cols[1]:
    if st.button("Run reactivation sweep now"):
        res = _post("/api/lifecycle/reactivate", {})
        if res is not None:
            st.success(
                f"Reactivated {len(res.get('reactivations', []))} symbol(s)."
            )
            if res.get("reactivations"):
                st.dataframe(res["reactivations"], use_container_width=True)
