"""Phases 44-45 — Learning Reports + Improvements page."""

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
st.set_page_config(page_title=f"{settings.app_name} — Learning Reports", layout="wide")
st.title("Learning Reports & Improvements")
st.caption(
    "Weekly summaries of what worked, what failed, and proposed improvements. "
    "Improvement suggestions require explicit approval — rules are never changed "
    "automatically."
)

def _render_report_summary(summary: dict) -> None:
    """Readable rendering of the weekly learning-report summary."""
    signals = summary.get("signals") or {}
    cols = st.columns(4)
    cols[0].metric("Signals", signals.get("total", 0))
    cols[1].metric("Evaluated", signals.get("evaluated", 0))
    cols[2].metric("Target hit", signals.get("successes_target_hit", 0))
    cols[3].metric("Stop hit", signals.get("failures_stop_hit", 0))

    rejected = summary.get("rejected_outcomes") or {}
    dnt = summary.get("do_not_touch_outcomes") or {}
    overrides = summary.get("user_overrides") or {}
    rows = [
        {"Bucket": "Rejected candidates", "Total": rejected.get("total", 0),
         "Correct": rejected.get("correct", 0), "Too strict": rejected.get("too_strict", 0)},
        {"Bucket": "Do-Not-Touch freezes", "Total": dnt.get("total", 0),
         "Correct": dnt.get("correct", 0), "Too strict": dnt.get("too_strict", 0)},
        {"Bucket": "User overrides", "Total": overrides.get("total", 0),
         "Correct": overrides.get("system_right", 0), "Too strict": overrides.get("user_right", 0)},
    ]
    st.dataframe(rows, use_container_width=True, hide_index=True)
    note = (summary.get("manual_option_input_usage") or {}).get("note")
    if note:
        st.caption(note)
    with st.expander("Full report payload", expanded=False):
        st.json(summary)


st.subheader("Weekly learning report")
if st.button("Generate weekly report"):
    result = post_json("/api/learning/reports/generate", {})
    if result is not None:
        st.success("Report generated.")
        _render_report_summary((result.get("result") or {}).get("summary") or {})

reports = get_json("/api/learning/reports")
if reports is not None and reports.get("reports"):
    latest = reports["reports"][0]
    st.write(f"Latest: {latest.get('period_start', '—')} → {latest.get('period_end', '—')}")
    _render_report_summary(latest.get("summary") or {})

st.divider()
st.subheader("Improvement suggestions (approval-gated)")
if st.button("Generate improvement suggestions"):
    result = post_json("/api/learning/improvements/generate", {})
    if result is not None:
        st.success(f"Suggestions: {result.get('result')}")

suggestions = get_json("/api/learning/improvements", status="PROPOSED")
if suggestions is not None and suggestions.get("suggestions"):
    for s in suggestions["suggestions"]:
        st.markdown(f"**{s['title']}** ({s['suggestion_type']})")
        st.write(s["rationale"])
        cols = st.columns(2)
        if cols[0].button("Approve", key=f"approve_{s['id']}"):
            post_json(f"/api/learning/improvements/{s['id']}/decide", {"approve": True})
            st.success("Approved (recorded; not auto-applied).")
        if cols[1].button("Reject", key=f"reject_{s['id']}"):
            post_json(f"/api/learning/improvements/{s['id']}/decide", {"approve": False})
            st.info("Rejected.")
        st.divider()
else:
    st.info("No proposed improvement suggestions.")

st.subheader("Champion / Challenger comparison")
cc = st.columns(2)
champ_rr = cc[0].number_input("Champion min R:R", value=2.0)
chall_rr = cc[1].number_input("Challenger min R:R", value=1.7)
if st.button("Compare rule versions (shadow test)"):
    result = post_json(
        "/api/learning/champion-challenger/compare",
        {"champion_min_risk_reward": champ_rr, "challenger_min_risk_reward": chall_rr},
    )
    if result is not None:
        st.json(result.get("comparison") or result)
