"""Phase 29, steps 29.3 / 29.4 — UI field priority manager + progressive panels.

Controls which fields are visible by default. Each field maps to a priority
tier:

* ``PRIMARY``   — always shown (the user-facing essentials);
* ``SECONDARY`` — shown in both modes but below the primaries;
* ``ADVANCED``  — hidden in beginner mode, revealed in advanced mode and inside
  progressive "details" panels.

Pure and Streamlit-free so it is unit-testable. Internal planning notes,
private discussion, and development artifacts are never registered here, so
they can never leak into the UI through this manager.
"""

from __future__ import annotations

from typing import Any

from app.ui_experience.view_mode import is_advanced

PRIMARY = "PRIMARY"
SECONDARY = "SECONDARY"
ADVANCED = "ADVANCED"

ALL_TIERS = frozenset({PRIMARY, SECONDARY, ADVANCED})

# Canonical field -> tier registry. Unknown fields default to SECONDARY so a
# new field is visible but never crowds out the primaries, and is never
# accidentally treated as advanced-only.
DEFAULT_FIELD_PRIORITIES: dict[str, str] = {
    # Primary essentials (Daily Opportunities first-visible fields, briefs, etc.)
    "symbol": PRIMARY,
    "ticker": PRIMARY,
    "final_action_label": PRIMARY,
    "final_label": PRIMARY,
    "instrument_scope": PRIMARY,
    "suggested_action_summary": PRIMARY,
    "priority_score": PRIMARY,
    "confidence_score": PRIMARY,
    "main_warning": PRIMARY,
    "option_data_warning": PRIMARY,
    "next_review_trigger": PRIMARY,
    "action_items": PRIMARY,
    "status": PRIMARY,
    "rejection_reason": PRIMARY,
    "freeze_reason": PRIMARY,
    "release_condition": PRIMARY,
    # Secondary context
    "lifecycle_state": SECONDARY,
    "option_expression_status": SECONDARY,
    "watch_condition": SECONDARY,
    "entry_condition": SECONDARY,
    "invalidation_condition": SECONDARY,
    "earnings_iv": SECONDARY,
    "news_events": SECONDARY,
    "severity": SECONDARY,
    "expires_at": SECONDARY,
    "stock_thesis": SECONDARY,
    # Advanced detail (hidden in beginner mode)
    "decision_trace": ADVANCED,
    "trace": ADVANCED,
    "checklist": ADVANCED,
    "confidence_breakdown": ADVANCED,
    "version_stamp": ADVANCED,
    "memory_details": ADVANCED,
    "similar_cases": ADVANCED,
    "context": ADVANCED,
    "raw": ADVANCED,
    "sufficiency_decision": ADVANCED,
    "hard_filter_decision": ADVANCED,
}


class FieldPriorityManager:
    def __init__(self, priorities: dict[str, str] | None = None) -> None:
        self.priorities = dict(DEFAULT_FIELD_PRIORITIES)
        if priorities:
            self.priorities.update(priorities)

    def priority_of(self, field: str) -> str:
        return self.priorities.get(field, SECONDARY)

    def is_visible(self, field: str, view_mode: str | None) -> bool:
        tier = self.priority_of(field)
        if tier == ADVANCED:
            return is_advanced(view_mode)
        return True

    def visible_fields(self, fields: list[str], view_mode: str | None) -> list[str]:
        """Return ``fields`` filtered + ordered (PRIMARY, SECONDARY, ADVANCED)."""
        tier_order = {PRIMARY: 0, SECONDARY: 1, ADVANCED: 2}
        visible = [f for f in fields if self.is_visible(f, view_mode)]
        return sorted(visible, key=lambda f: (tier_order[self.priority_of(f)], fields.index(f)))

    def partition(
        self, record: dict[str, Any], view_mode: str | None
    ) -> dict[str, dict[str, Any]]:
        """Split a record into primary / secondary / advanced sub-dicts.

        Advanced fields are always returned in the ``advanced`` bucket (so a
        progressive details panel can render them on demand) but are only
        surfaced in the primary view when ``view_mode`` is advanced.
        """
        buckets: dict[str, dict[str, Any]] = {
            PRIMARY: {},
            SECONDARY: {},
            ADVANCED: {},
        }
        for key, value in record.items():
            buckets[self.priority_of(key)][key] = value
        return {
            "primary": buckets[PRIMARY],
            "secondary": buckets[SECONDARY],
            "advanced": buckets[ADVANCED],
        }


__all__ = [
    "ADVANCED",
    "ALL_TIERS",
    "DEFAULT_FIELD_PRIORITIES",
    "FieldPriorityManager",
    "PRIMARY",
    "SECONDARY",
]
