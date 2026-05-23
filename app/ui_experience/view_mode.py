"""Phase 29, step 29.5 — beginner / advanced view mode.

Pure, importable (no Streamlit dependency) so it can be unit-tested and reused
by every page. Beginner mode hides advanced fields (traces, raw details,
confidence breakdowns, memory details, version details); advanced mode exposes
them.
"""

from __future__ import annotations

VIEW_BEGINNER = "BEGINNER"
VIEW_ADVANCED = "ADVANCED"

ALL_VIEW_MODES = frozenset({VIEW_BEGINNER, VIEW_ADVANCED})
DEFAULT_VIEW_MODE = VIEW_BEGINNER


def normalize_view_mode(value: str | None) -> str:
    """Coerce arbitrary input to a valid view mode (default BEGINNER)."""
    if value is None:
        return DEFAULT_VIEW_MODE
    candidate = str(value).strip().upper()
    return candidate if candidate in ALL_VIEW_MODES else DEFAULT_VIEW_MODE


def is_advanced(view_mode: str | None) -> bool:
    return normalize_view_mode(view_mode) == VIEW_ADVANCED


__all__ = [
    "ALL_VIEW_MODES",
    "DEFAULT_VIEW_MODE",
    "VIEW_ADVANCED",
    "VIEW_BEGINNER",
    "is_advanced",
    "normalize_view_mode",
]
