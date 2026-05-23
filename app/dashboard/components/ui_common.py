"""Phase 29 — shared Streamlit UI widgets (view switcher, manual option shortcut).

Runtime-only (imports Streamlit lazily inside each function). The pure logic
these widgets rely on lives in ``app.ui_experience`` so it can be tested
without Streamlit.
"""

from __future__ import annotations

from typing import Any

from app.dashboard.components.api_client import post_json
from app.ui_experience.field_priority import FieldPriorityManager
from app.ui_experience.view_mode import (
    DEFAULT_VIEW_MODE,
    VIEW_ADVANCED,
    VIEW_BEGINNER,
    is_advanced,
)


def view_mode_selector(*, key: str = "global_view_mode") -> str:
    """Render the beginner/advanced switcher in the sidebar; return the mode."""
    import streamlit as st

    options = [VIEW_BEGINNER, VIEW_ADVANCED]
    current = st.session_state.get(key, DEFAULT_VIEW_MODE)
    choice = st.sidebar.radio(
        "View mode",
        options,
        index=options.index(current) if current in options else 0,
        key=key,
        help=(
            "Beginner hides advanced detail (traces, confidence breakdowns, "
            "version stamps). Advanced reveals everything."
        ),
    )
    return choice


def render_progressive_record(
    record: dict[str, Any],
    view_mode: str,
    *,
    manager: FieldPriorityManager | None = None,
    advanced_label: str = "Advanced detail",
) -> None:
    """Render a record's primary fields, with advanced fields behind an expander."""
    import streamlit as st

    manager = manager or FieldPriorityManager()
    parts = manager.partition(record, view_mode)

    for key, value in {**parts["primary"], **parts["secondary"]}.items():
        st.write(f"**{key}**: {value}")

    if parts["advanced"]:
        if is_advanced(view_mode):
            with st.expander(advanced_label, expanded=False):
                st.json(parts["advanced"])
        else:
            with st.expander(f"{advanced_label} (advanced mode)", expanded=False):
                st.json(parts["advanced"])


def render_kv(record: dict[str, Any], *, skip: tuple[str, ...] = ()) -> None:
    """Render a flat-ish dict as readable ``**Label**: value`` lines.

    ``None`` values and ``skip`` keys are omitted; nested dicts/lists are
    rendered with Streamlit's native object renderer below their label.
    """
    import streamlit as st

    for key, value in record.items():
        if key in skip or value is None:
            continue
        label = str(key).replace("_", " ").capitalize()
        if isinstance(value, dict | list):
            st.write(f"**{label}**")
            st.write(value)
        else:
            st.write(f"**{label}**: {value}")


def manual_option_shortcut(
    symbol_default: str = "",
    *,
    key_prefix: str = "manual_opt",
) -> None:
    """Phase 29.10 — paste manual option text from Home / ticker pages."""
    import streamlit as st

    st.caption(
        "Paste free-form option data (symbol, expiration, strike, call/put, "
        "bid, ask, last, IV, delta, gamma, theta, vega, volume, open interest). "
        "Missing fields are shown honestly and never invented."
    )
    symbol = st.text_input(
        "Symbol (optional — parser can infer)",
        value=symbol_default,
        key=f"{key_prefix}_symbol",
    )
    raw_text = st.text_area("Option text", key=f"{key_prefix}_text", height=140)
    if st.button("Parse / Analyze Option Data", key=f"{key_prefix}_submit"):
        if not raw_text.strip():
            st.warning("Paste some option text first.")
            return
        body: dict[str, Any] = {"raw_text": raw_text}
        if symbol.strip():
            body["symbol"] = symbol.strip().upper()
        result = post_json("/api/options/manual-input", body)
        if result is not None:
            st.success("Option text parsed and stored.")
            with st.expander("Parsed fields (raw diagnostics)", expanded=False):
                st.json(result)


__all__ = [
    "manual_option_shortcut",
    "render_kv",
    "render_progressive_record",
    "view_mode_selector",
]
