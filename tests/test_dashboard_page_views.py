"""Phases 30-32 — tests for the pure page-view builders.

These protect the display contract of the Daily Opportunities, Rejected But
Interesting, and Do-Not-Touch pages — including the critical invariant that
missing option data is a *prompt*, never a rejection, and that contract-level
option failures only surface when option data was actually evaluated.
"""

from __future__ import annotations

from app.ui_experience.page_views import (
    build_freeze_row,
    build_opportunity_row,
    build_rejected_row,
    option_data_was_evaluated,
)

# --- Phase 30: Daily Opportunities -----------------------------------------


def test_opportunity_row_first_visible_fields() -> None:
    suggestion = {
        "symbol": "AMD",
        "final_action_label": "READY_TO_RESEARCH_STOCK_ONLY",
        "instrument_scope": "STOCK_ONLY",
        "suggested_action_summary": "Research AMD now.",
        "priority_score": 80.0,
        "confidence_score": 70.0,
        "manual_option_input_needed": False,
        "option_expression_status": "OPTION_EXPR_NOT_EVALUATED",
        "next_review_trigger": {"trigger_type": "PRICE_ENTERED_ZONE"},
        "action_items": [{"description": "Check entry zone"}],
        "lifecycle_state": "READY_FOR_RESEARCH",
    }
    row = build_opportunity_row(suggestion)
    assert row["ticker"] == "AMD"
    assert row["final_action_label"] == "READY_TO_RESEARCH_STOCK_ONLY"
    assert row["instrument_scope_label"] == "Stock only"
    assert row["priority_score"] == 80.0
    assert row["confidence_score"] == 70.0
    assert row["next_review_trigger"] == "PRICE_ENTERED_ZONE"
    assert row["action_items"]


def test_opportunity_row_missing_option_is_prompt_not_rejection() -> None:
    suggestion = {
        "symbol": "NVDA",
        "final_action_label": "OPTION_DATA_NOT_AVAILABLE",
        "instrument_scope": "STOCK_ONLY",
        "manual_option_input_needed": True,
        "option_expression_status": "OPTION_EXPR_NOT_EVALUATED",
    }
    row = build_opportunity_row(suggestion)
    assert row["option_data_warning"] is not None
    assert "reject" not in row["option_data_warning"].lower()


# --- Phase 31: Rejected But Interesting -------------------------------------


def test_option_failure_shown_only_when_option_evaluated() -> None:
    with_option = {
        "symbol": "TSLA",
        "rejection_category": "STOCK_OK_OPTION_BAD",
        "reasons": [
            {"reason_label": "BREAKEVEN_TOO_FAR", "reason_category": "OPTION",
             "explanation": "Breakeven 12% away."},
        ],
    }
    assert option_data_was_evaluated(with_option) is True
    row = build_rejected_row(with_option)
    assert row["show_option_failure"] is True
    assert row["option_failures"]


def test_missing_option_data_does_not_show_option_failure() -> None:
    # Stock-good / option-missing — no OPTION reason category present.
    missing_option = {
        "symbol": "AMD",
        "rejection_category": "HARD_STOCK_REJECTION",
        "reasons": [
            {"reason_label": "RISK_REWARD_TOO_LOW", "reason_category": "STOCK",
             "explanation": "R:R below minimum."},
        ],
    }
    assert option_data_was_evaluated(missing_option) is False
    row = build_rejected_row(missing_option)
    assert row["show_option_failure"] is False
    assert row["option_failures"] == []
    assert row["stock_reasons"] == ["RISK_REWARD_TOO_LOW"]


def test_rejected_row_preserves_interesting_flag() -> None:
    candidate = {
        "symbol": "INTC",
        "rejection_category": "STOCK_OK_OPTION_BAD",
        "is_rejected_but_interesting": True,
        "interesting_reasons": ["stock thesis still valid"],
        "reasons": [],
    }
    row = build_rejected_row(candidate)
    assert row["is_rejected_but_interesting"] is True
    assert row["interesting_reasons"] == ["stock thesis still valid"]


# --- Phase 32: Do-Not-Touch -------------------------------------------------


def test_freeze_row_fields() -> None:
    item = {
        "symbol": "BADCO",
        "reason_summary": "Extreme IV.",
        "freeze_category": "EXTREME_OPTION_VOLATILITY",
        "freeze_severity": "HARD_FREEZE",
        "expires_at": "2026-05-27T00:00:00+00:00",
        "release_condition_label": "TIME_RELEASE",
        "release_condition_description": "Releases after the freeze window.",
    }
    row = build_freeze_row(item)
    assert row["ticker"] == "BADCO"
    assert row["severity"] == "HARD_FREEZE"
    assert row["expires_at"] == "2026-05-27T00:00:00+00:00"
    assert row["release_condition"] == "TIME_RELEASE"
