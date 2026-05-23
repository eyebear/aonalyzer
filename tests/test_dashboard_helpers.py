"""Phase 29, step 29.15 — tests for dashboard rendering helpers + UI experience.

These cover the pure, Streamlit-free logic behind progressive disclosure, the
beginner/advanced switcher, the field-priority manager, and the shared render
helpers (option-data warning derivation, worklist grouping, score formatting).
"""

from __future__ import annotations

from app.ui_experience.field_priority import (
    ADVANCED,
    PRIMARY,
    SECONDARY,
    FieldPriorityManager,
)
from app.ui_experience.render_helpers import (
    format_score,
    group_worklist_by_type,
    instrument_scope_label,
    option_data_warning,
    priority_badge,
    sort_worklist_items,
    summarize_worklist,
)
from app.ui_experience.view_mode import (
    DEFAULT_VIEW_MODE,
    VIEW_ADVANCED,
    VIEW_BEGINNER,
    is_advanced,
    normalize_view_mode,
)

# --- view mode -------------------------------------------------------------


def test_normalize_view_mode_defaults_to_beginner() -> None:
    assert normalize_view_mode(None) == VIEW_BEGINNER
    assert normalize_view_mode("garbage") == VIEW_BEGINNER
    assert DEFAULT_VIEW_MODE == VIEW_BEGINNER


def test_normalize_view_mode_accepts_advanced() -> None:
    assert normalize_view_mode("advanced") == VIEW_ADVANCED
    assert is_advanced(VIEW_ADVANCED) is True
    assert is_advanced(VIEW_BEGINNER) is False


# --- field priority --------------------------------------------------------


def test_advanced_fields_hidden_in_beginner_mode() -> None:
    mgr = FieldPriorityManager()
    assert mgr.priority_of("decision_trace") == ADVANCED
    assert mgr.is_visible("decision_trace", VIEW_BEGINNER) is False
    assert mgr.is_visible("decision_trace", VIEW_ADVANCED) is True


def test_primary_fields_always_visible() -> None:
    mgr = FieldPriorityManager()
    for field in ("symbol", "final_action_label", "suggested_action_summary"):
        assert mgr.priority_of(field) == PRIMARY
        assert mgr.is_visible(field, VIEW_BEGINNER) is True


def test_unknown_field_defaults_to_secondary_and_visible() -> None:
    mgr = FieldPriorityManager()
    assert mgr.priority_of("some_new_field") == SECONDARY
    assert mgr.is_visible("some_new_field", VIEW_BEGINNER) is True


def test_partition_splits_record() -> None:
    mgr = FieldPriorityManager()
    record = {
        "symbol": "AMD",
        "lifecycle_state": "WATCHING",
        "decision_trace": [{"step": 1}],
        "version_stamp": {"rule_version": "x"},
    }
    parts = mgr.partition(record, VIEW_BEGINNER)
    assert "symbol" in parts["primary"]
    assert "lifecycle_state" in parts["secondary"]
    assert "decision_trace" in parts["advanced"]
    assert "version_stamp" in parts["advanced"]


def test_visible_fields_ordered_primary_first() -> None:
    mgr = FieldPriorityManager()
    fields = ["decision_trace", "lifecycle_state", "symbol"]
    visible = mgr.visible_fields(fields, VIEW_ADVANCED)
    assert visible[0] == "symbol"  # primary first
    assert visible[-1] == "decision_trace"  # advanced last


# --- render helpers --------------------------------------------------------


def test_format_score_handles_none() -> None:
    assert format_score(None) == "—"
    assert format_score(72.345) == "72.3"


def test_priority_badge() -> None:
    assert "HIGH" in priority_badge("high")
    assert priority_badge(None) == "—"


def test_instrument_scope_label() -> None:
    assert instrument_scope_label("STOCK_ONLY") == "Stock only"
    assert instrument_scope_label("OPTION_REJECTED") == "Option rejected"
    assert instrument_scope_label(None) == "—"


def test_option_data_warning_missing_data_is_prompt_not_rejection() -> None:
    warning = option_data_warning(
        option_expression_status="OPTION_EXPR_NOT_EVALUATED",
        manual_option_input_needed=True,
    )
    assert warning is not None
    assert "Option data not available" in warning
    # Not a rejection wording.
    assert "reject" not in warning.lower()


def test_option_data_warning_none_when_evaluated_ok() -> None:
    assert (
        option_data_warning(
            option_expression_status="OPTION_EXPR_OK",
            manual_option_input_needed=False,
            has_manual_snapshot=True,
        )
        is None
    )


def test_option_data_warning_failed_contract() -> None:
    warning = option_data_warning(
        option_expression_status="OPTION_EXPR_BAD",
        manual_option_input_needed=False,
    )
    assert warning is not None
    assert "failed suitability" in warning


def test_group_and_summarize_worklist() -> None:
    items = [
        {"worklist_type": "RISK_ALERT", "symbol": "A", "priority": "HIGH", "rank": 1},
        {"worklist_type": "ACTION_READY", "symbol": "B", "priority": "HIGH", "rank": 2},
        {"worklist_type": "ACTION_READY", "symbol": "C", "priority": "HIGH", "rank": 3},
    ]
    grouped = group_worklist_by_type(items)
    # RISK_ALERT sorts before ACTION_READY in type order.
    assert list(grouped.keys())[0] == "RISK_ALERT"
    summary = summarize_worklist(items)
    assert summary["ACTION_READY"] == 2
    assert summary["RISK_ALERT"] == 1


def test_sort_worklist_items_by_rank() -> None:
    items = [
        {"worklist_type": "ACTION_READY", "symbol": "B", "priority": "HIGH", "rank": 3},
        {"worklist_type": "RISK_ALERT", "symbol": "A", "priority": "HIGH", "rank": 1},
    ]
    ordered = sort_worklist_items(items)
    assert ordered[0]["rank"] == 1
