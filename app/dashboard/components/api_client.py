"""Phase 29 — shared dashboard API client helpers.

Thin wrappers over the FastAPI service used by every Streamlit page so the
``_get`` / ``_post`` pattern is defined once. Imports Streamlit only for the
inline warning surface; safe to import inside ``streamlit run`` pages.
"""

from __future__ import annotations

from typing import Any

import requests

from app.core.config import get_settings

settings = get_settings()


def api_base_url() -> str:
    return settings.api_base_url


def get_json(path: str, *, timeout: int = 15, **params: Any) -> dict | None:
    import streamlit as st

    try:
        response = requests.get(
            f"{settings.api_base_url}{path}", params=params, timeout=timeout
        )
    except requests.RequestException as exc:
        st.warning(f"Could not reach {path}: {exc}")
        return None
    if response.status_code != 200:
        st.warning(f"{path} returned status {response.status_code}.")
        return None
    return response.json()


def post_json(path: str, body: dict | None = None, *, timeout: int = 20) -> dict | None:
    import streamlit as st

    try:
        response = requests.post(
            f"{settings.api_base_url}{path}", json=body or {}, timeout=timeout
        )
    except requests.RequestException as exc:
        st.warning(f"Could not reach {path}: {exc}")
        return None
    if response.status_code != 200:
        st.warning(f"{path} returned status {response.status_code}.")
        return None
    return response.json()


__all__ = ["api_base_url", "get_json", "post_json"]
