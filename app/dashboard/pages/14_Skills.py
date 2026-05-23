"""Phase 43 — Skills page."""

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
st.set_page_config(page_title=f"{settings.app_name} — Skills", layout="wide")
st.title("Skills & Performance")
st.caption(
    "System analysis skills and their measured performance. Metrics are "
    "recorded and exposed; skill behavior is never silently changed by them."
)

if st.button("Register + recompute skill performance"):
    result = post_json("/api/memory/skills/compute", {})
    if result is not None:
        st.success(f"Computed: {result['result']}")

skills = get_json("/api/memory/skills")
if skills is not None and skills.get("skills"):
    rows = []
    for s in skills["skills"]:
        perf = s.get("performance") or {}
        rows.append(
            {
                "Skill": s["skill_name"],
                "Category": s["category"],
                "Sample": perf.get("sample_size"),
                "Target hit rate": perf.get("target_hit_rate"),
                "Stop-first rate": perf.get("stop_first_rate"),
                "Stock-right/option-wrong": perf.get("stock_right_option_wrong_rate"),
                "Option reader usefulness": perf.get("manual_option_reader_usefulness"),
                "EV proxy": perf.get("expected_value_proxy"),
            }
        )
    st.dataframe(rows, use_container_width=True)
else:
    st.info("No skills registered yet. Click the button above.")
