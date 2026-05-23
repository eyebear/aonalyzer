"""Phase 47 — Settings page."""

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
st.set_page_config(page_title=f"{settings.app_name} — Settings", layout="wide")
st.title("Settings")
st.caption(
    "Platform settings. Safe default: missing option data never blocks "
    "stock-only research (allow_stock_only_when_options_missing stays true)."
)

current = get_json("/api/settings/platform")
values = (current or {}).get("settings", {})

st.subheader("Manual option behavior")
mo_enabled = st.checkbox(
    "Manual option input enabled",
    value=bool(values.get("manual_option_input_enabled", True)),
)
ai_reader = st.checkbox(
    "Option text AI reader enabled",
    value=bool(values.get("option_text_ai_reader_enabled", True)),
)
strict = st.checkbox(
    "Strict option parser mode",
    value=bool(values.get("strict_option_parser_mode", False)),
)
allow_stock_only = st.checkbox(
    "Allow stock-only when options missing (recommended ON)",
    value=bool(values.get("allow_stock_only_when_options_missing", True)),
)

st.subheader("Schedule & risk filters")
md_minutes = st.number_input(
    "Market data refresh (minutes)",
    value=int(values.get("market_data_refresh_minutes", 30)),
    min_value=1,
)
spread = st.number_input(
    "Option max spread %",
    value=float(values.get("option_max_spread_percent", 10.0)),
)

col_save, col_reset = st.columns(2)
if col_save.button("Save settings"):
    body = {
        "manual_option_input_enabled": mo_enabled,
        "option_text_ai_reader_enabled": ai_reader,
        "strict_option_parser_mode": strict,
        "allow_stock_only_when_options_missing": allow_stock_only,
        "market_data_refresh_minutes": int(md_minutes),
        "option_max_spread_percent": float(spread),
    }
    result = post_json("/api/settings/platform", body)
    if result is not None:
        st.success("Settings saved.")

if col_reset.button("Reset all to defaults"):
    result = post_json("/api/settings/platform/reset", {})
    if result is not None:
        st.success("Settings reset to defaults.")

st.subheader("Effective settings")
if values:
    st.dataframe(
        [{"Setting": key, "Value": str(value)} for key, value in sorted(values.items())],
        use_container_width=True,
        hide_index=True,
    )
else:
    st.info("No stored setting overrides — defaults are in effect.")
