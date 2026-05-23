"""Phase 24, step 24.9 — Do-Not-Touch dashboard page.

Streamlit page that surfaces the active freezes + recent history for a
chosen symbol. Calls the FastAPI endpoints rather than touching the DB
directly, mirroring the pattern used by ``app/dashboard/main.py``.

This file is loaded only by the Streamlit runtime (``streamlit run``);
it is not imported by the FastAPI app or by pytest. Keep all Streamlit
calls inside the module body so a missing streamlit import only breaks
this page, never the rest of the codebase.
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

st.set_page_config(page_title=f"{settings.app_name} — Do-Not-Touch", layout="wide")
st.title("Do-Not-Touch")
st.caption(
    "Active risk freezes and their release conditions. Missing option data "
    "alone never creates a freeze; extreme pasted option risk can."
)


def _get(path: str, **params) -> dict | None:
    url = f"{settings.api_base_url}{path}"
    try:
        response = requests.get(url, params=params, timeout=10)
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
        response = requests.post(url, json=body or {}, timeout=10)
    except requests.RequestException as exc:
        st.warning(f"Failed to call {path}: {exc}")
        return None
    if response.status_code != 200:
        st.warning(f"{path} returned status {response.status_code}.")
        return None
    return response.json()


# --- Active freezes --------------------------------------------------------

st.subheader("Active freezes")

active_response = _get("/api/do-not-touch")
if active_response is not None:
    items = active_response.get("items", [])
    if not items:
        st.info("No symbols are currently frozen.")
    else:
        st.dataframe(
            [
                {
                    "Symbol": item["symbol"],
                    "Category": item["freeze_category"],
                    "Severity": item["freeze_severity"],
                    "Frozen at": item["frozen_at"],
                    "Expires at": item["expires_at"] or "—",
                    "Release condition": item["release_condition_label"],
                    "Reason": item["reason_summary"],
                }
                for item in items
            ],
            use_container_width=True,
        )

# --- Sweep expired ---------------------------------------------------------

st.subheader("Expiration sweep")

if st.button("Run expiration sweep now"):
    sweep = _post("/api/do-not-touch/sweep-expired")
    if sweep is not None:
        st.success(
            f"Released {sweep['result']['swept_count']} expired freeze(s)."
        )
        if sweep["result"]["released_symbols"]:
            st.write(", ".join(sweep["result"]["released_symbols"]))

# --- Per-symbol inspector --------------------------------------------------

st.subheader("Inspect a symbol")

symbol_input = st.text_input("Symbol", value="AMD").strip().upper()
col_eval, col_freeze, col_release = st.columns(3)

with col_eval:
    if st.button("Classify freeze now (dry-run)"):
        if symbol_input:
            evaluation = _get(f"/api/do-not-touch/{symbol_input}", persist="false")
            if evaluation is not None:
                st.json(evaluation)
    # Phase 32.6 — re-check: re-evaluate and apply (a freeze whose conditions
    # no longer hold is released).
    if st.button("Re-check (re-evaluate & apply)"):
        if symbol_input:
            evaluation = _get(f"/api/do-not-touch/{symbol_input}", persist="true")
            if evaluation is not None:
                active = evaluation.get("active_freeze")
                if active:
                    st.warning(
                        f"{symbol_input} remains frozen: {active['reason_summary']}"
                    )
                else:
                    st.success(f"{symbol_input} is not frozen after re-check.")

with col_freeze:
    freeze_reason = st.text_input(
        "Manual freeze reason", value="Manual freeze applied by user."
    )
    if st.button("Manual freeze"):
        if symbol_input:
            res = _post(
                f"/api/do-not-touch/{symbol_input}/freeze",
                {"reason": freeze_reason, "severity": "HARD_FREEZE"},
            )
            if res is not None:
                st.success(f"Frozen {symbol_input}.")
                st.json(res)

with col_release:
    release_reason = st.text_input(
        "Release reason", value="Manual release by user."
    )
    if st.button("Manual release"):
        if symbol_input:
            res = _post(
                f"/api/do-not-touch/{symbol_input}/release",
                {"reason": release_reason},
            )
            if res is not None:
                st.success(f"Released {symbol_input}.")
                st.json(res)

# --- History --------------------------------------------------------------

st.subheader("History")
if symbol_input:
    history_response = _get(f"/api/do-not-touch/history/{symbol_input}")
    if history_response is not None and history_response.get("history"):
        st.dataframe(
            [
                {
                    "Created": row["created_at"],
                    "Event": row["event_type"],
                    "Category": row["freeze_category"],
                    "Severity": row["freeze_severity"],
                    "Reason": row["reason_summary"],
                    "Triggered by": row["triggered_by"],
                    "Source": row["source_phase"],
                }
                for row in history_response["history"]
            ],
            use_container_width=True,
        )
    else:
        st.info(f"No history for {symbol_input}.")

# --- Memory: did similar freezes work? (Phase 32.8) ------------------------

st.subheader("Similar freeze memory")
if symbol_input:
    # Case memory (Phase 41) records whether past freezes avoided bad outcomes.
    cases = _get("/api/memory/cases", symbol=symbol_input, case_type="DO_NOT_TOUCH")
    if cases is not None and cases.get("cases"):
        st.dataframe(
            [
                {
                    "Outcome": c.get("outcome_type"),
                    "Lesson": c.get("lesson_summary"),
                    "Created": c.get("created_at"),
                }
                for c in cases["cases"]
            ],
            use_container_width=True,
        )
    else:
        st.caption(
            "No similar freeze outcomes stored yet. Freeze quality is learned "
            "as Do-Not-Touch outcomes are tracked over time."
        )
