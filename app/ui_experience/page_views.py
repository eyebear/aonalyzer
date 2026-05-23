"""Phases 30-32 — pure page-view builders (Streamlit-free, testable).

Transform API response dicts into the display rows each page renders. Keeping
this logic here lets us unit-test the *display contract* (first-visible fields,
option-data warnings, rejection distinctions, freeze formatting) without
importing Streamlit.
"""

from __future__ import annotations

from typing import Any

from app.ui_experience.render_helpers import (
    instrument_scope_label,
    option_data_warning,
)

# Reason categories that mean "option data was actually evaluated and failed".
_OPTION_REASON_CATEGORIES = frozenset({"OPTION", "REASON_CATEGORY_OPTION"})
_STOCK_REASON_CATEGORIES = frozenset({"STOCK", "REASON_CATEGORY_STOCK"})


# --- Phase 30: Daily Opportunities -----------------------------------------


def build_opportunity_row(suggestion: dict[str, Any]) -> dict[str, Any]:
    """Phase 30 — first-visible fields for one Daily Opportunity row.

    Order matches step 30.x: ticker, final action label, instrument scope,
    suggested action summary, priority score, confidence score, main warning,
    next review trigger, action items. Missing option data surfaces as a
    *warning/prompt*, never a rejection.
    """
    next_review = suggestion.get("next_review_trigger") or {}
    warning = option_data_warning(
        option_expression_status=suggestion.get("option_expression_status"),
        manual_option_input_needed=bool(suggestion.get("manual_option_input_needed")),
    )
    return {
        "ticker": suggestion.get("symbol"),
        "final_action_label": suggestion.get("final_action_label"),
        "instrument_scope": suggestion.get("instrument_scope"),
        "instrument_scope_label": instrument_scope_label(
            suggestion.get("instrument_scope")
        ),
        "suggested_action_summary": suggestion.get("suggested_action_summary"),
        "priority_score": suggestion.get("priority_score"),
        "confidence_score": suggestion.get("confidence_score"),
        "option_data_warning": warning,
        "next_review_trigger": _next_review_text(next_review),
        "action_items": suggestion.get("action_items", []),
        "lifecycle_state": suggestion.get("lifecycle_state"),
    }


def _next_review_text(next_review: Any) -> str:
    """Always return readable text for the next-review column, never a dict."""
    if not next_review:
        return "—"
    if isinstance(next_review, str):
        return next_review
    if isinstance(next_review, dict):
        for key in ("trigger_type", "label", "description", "summary"):
            value = next_review.get(key)
            if value:
                return str(value)
        scalars = [
            f"{key}: {value}"
            for key, value in next_review.items()
            if value not in (None, "", [], {}) and not isinstance(value, dict | list)
        ]
        return "; ".join(scalars) if scalars else "—"
    return str(next_review)


# --- Phase 31: Rejected But Interesting -------------------------------------


def option_data_was_evaluated(candidate: dict[str, Any]) -> bool:
    """True only if the rejection includes a real option-side failure reason.

    Missing option data never produces an OPTION reason (the classifier emits
    a non-rejection ``stock-ok-option-missing`` result instead), so this stays
    False for a stock-good/option-missing candidate.
    """
    reasons = candidate.get("reasons", []) or []
    return any(
        (r.get("reason_category") or "").upper() in _OPTION_REASON_CATEGORIES
        for r in reasons
    )


def build_rejected_row(candidate: dict[str, Any]) -> dict[str, Any]:
    """Phase 31 — display row for a rejected / partially-rejected candidate."""
    reasons = candidate.get("reasons", []) or []
    show_option_failure = option_data_was_evaluated(candidate)

    option_failures = (
        [
            {
                "reason_label": r.get("reason_label"),
                "explanation": r.get("explanation"),
            }
            for r in reasons
            if (r.get("reason_category") or "").upper() in _OPTION_REASON_CATEGORIES
        ]
        if show_option_failure
        else []
    )
    stock_reasons = [
        r.get("reason_label")
        for r in reasons
        if (r.get("reason_category") or "").upper() in _STOCK_REASON_CATEGORIES
    ]
    main_reason = reasons[0].get("reason_label") if reasons else candidate.get("summary")

    return {
        "ticker": candidate.get("symbol"),
        "rejection_category": candidate.get("rejection_category"),
        "rejection_severity": candidate.get("rejection_severity"),
        "is_rejected_but_interesting": bool(
            candidate.get("is_rejected_but_interesting")
        ),
        "interesting_reasons": candidate.get("interesting_reasons", []),
        "main_rejection_reason": main_reason,
        "stock_reasons": stock_reasons,
        "show_option_failure": show_option_failure,
        "option_failures": option_failures,
        "summary": candidate.get("summary"),
    }


# --- Phase 32: Do-Not-Touch -------------------------------------------------


def build_freeze_row(item: dict[str, Any]) -> dict[str, Any]:
    """Phase 32 — display row for an active Do-Not-Touch freeze."""
    return {
        "ticker": item.get("symbol"),
        "freeze_reason": item.get("reason_summary"),
        "freeze_category": item.get("freeze_category"),
        "severity": item.get("freeze_severity"),
        "expires_at": item.get("expires_at"),
        "release_condition": item.get("release_condition_label"),
        "release_condition_description": item.get("release_condition_description"),
    }


__all__ = [
    "build_freeze_row",
    "build_opportunity_row",
    "build_rejected_row",
    "option_data_was_evaluated",
]
