"""Phase 48 — Memory Export / Import page."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.dashboard.components.api_client import post_json  # noqa: E402

settings = get_settings()
st.set_page_config(page_title=f"{settings.app_name} — Memory Export/Import", layout="wide")
st.title("Memory Export / Import")
st.caption(
    "Back up and restore the system's learned memory. Imports validate the "
    "package structure before restoring any records."
)

st.subheader("Export")
if st.button("Export memory package"):
    result = post_json("/api/export-import/export", {})
    if result is not None:
        body = result.get("result") or {}
        st.success(f"Exported to {body.get('package_path', '(unknown path)')}")
        with st.expander("Package manifest (raw diagnostics)", expanded=False):
            st.json(body.get("manifest") or {})

st.subheader("Validate / Import")
package_dir = st.text_input("Package directory")
cols = st.columns(2)
if cols[0].button("Validate package") and package_dir:
    result = post_json("/api/export-import/validate", {"package_dir": package_dir})
    if result is not None:
        validation = result.get("validation") or {}
        if validation.get("is_valid", validation.get("valid")):
            st.success("Package is valid.")
        else:
            st.warning("Package validation reported problems — see diagnostics.")
        with st.expander("Raw diagnostics", expanded=False):
            st.json(validation)
if cols[1].button("Import package") and package_dir:
    result = post_json("/api/export-import/import", {"package_dir": package_dir})
    if result is not None:
        st.success("Import finished.")
        with st.expander("Raw diagnostics", expanded=False):
            st.json(result.get("result") or {})
