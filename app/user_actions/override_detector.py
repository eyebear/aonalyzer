"""Phase 38, step 38.5 — override detector (pure, deterministic).

Detects when a user action goes against the system suggestion. It does NOT
judge the action — judgement happens later from real outcomes. Returns the
override type or ``None`` when the action is consistent with the suggestion.
"""

from __future__ import annotations

from app.user_actions.user_action_types import (
    ACT_ACTIONS,
    OVERRIDE_IGNORED_RECOMMENDATION,
    OVERRIDE_TRADED_AGAINST_REJECTION,
    PASS_ACTIONS,
    SYSTEM_READY_LABELS,
    SYSTEM_REJECTION_LABELS,
)


def detect_override(
    *, system_suggestion_label: str | None, user_action_type: str
) -> str | None:
    """Return the override type, or ``None`` if the action agrees with the system."""
    label = (system_suggestion_label or "").upper()
    action = (user_action_type or "").upper()

    # User traded despite a system rejection / no-trade verdict.
    if label in SYSTEM_REJECTION_LABELS and action in ACT_ACTIONS:
        return OVERRIDE_TRADED_AGAINST_REJECTION

    # User passed on a clear system recommendation.
    if label in SYSTEM_READY_LABELS and action in PASS_ACTIONS:
        return OVERRIDE_IGNORED_RECOMMENDATION

    return None


__all__ = ["detect_override"]
