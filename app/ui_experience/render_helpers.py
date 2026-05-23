"""Phase 29, step 29.15 — pure rendering helpers (Streamlit-free, testable).

Formatting, grouping, and warning-derivation helpers shared by the dashboard
pages. Keeping them here (instead of inside ``streamlit run`` page files) means
they can be unit-tested and reused without importing Streamlit.
"""

from __future__ import annotations

from typing import Any

from app.worklist.worklist_types import priority_rank, type_rank

# Instrument scope display labels.
_SCOPE_LABELS = {
    "STOCK_ONLY": "Stock only",
    "SCOPE_STOCK_ONLY": "Stock only",
    "OPTION_AVAILABLE": "Option available",
    "SCOPE_OPTION_AVAILABLE": "Option available",
    "OPTION_REJECTED": "Option rejected",
    "SCOPE_OPTION_REJECTED": "Option rejected",
}

_PRIORITY_BADGES = {
    "HIGH": "🔴 HIGH",
    "MEDIUM": "🟠 MEDIUM",
    "LOW": "🟡 LOW",
}


def format_score(value: float | None) -> str:
    """Format a 0-100 score; absent values render as an em dash."""
    if value is None:
        return "—"
    return f"{float(value):.1f}"


def priority_badge(priority: str | None) -> str:
    if priority is None:
        return "—"
    return _PRIORITY_BADGES.get(priority.upper(), priority)


def instrument_scope_label(scope: str | None) -> str:
    if scope is None:
        return "—"
    return _SCOPE_LABELS.get(scope.upper(), scope)


def option_data_warning(
    *,
    option_expression_status: str | None,
    manual_option_input_needed: bool,
    has_manual_snapshot: bool = False,
) -> str | None:
    """Phase 30.10 — describe whether option data was missing or parsed.

    Returns a *warning/prompt* string (never a rejection). Returns ``None``
    when option data was successfully parsed and evaluated.
    """
    status = (option_expression_status or "").upper()
    if status == "OPTION_EXPR_BAD":
        return "Option contract was parsed but failed suitability filters."
    if status in ("OPTION_EXPR_OK",) and has_manual_snapshot:
        return None
    if manual_option_input_needed or status in (
        "OPTION_EXPR_NOT_EVALUATED",
        "NOT_EVALUATED",
        "OPTION_DATA_NOT_AVAILABLE",
        "",
    ):
        return (
            "Option data not available — paste a manual option contract to "
            "evaluate the option side. Stock-only analysis still applies."
        )
    return None


def group_worklist_by_type(items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Group worklist items by ``worklist_type`` in deterministic type order."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        grouped.setdefault(item.get("worklist_type", "UNKNOWN"), []).append(item)
    return dict(
        sorted(grouped.items(), key=lambda kv: type_rank(kv[0]))
    )


def summarize_worklist(items: list[dict[str, Any]]) -> dict[str, int]:
    """Return a {worklist_type: count} summary."""
    summary: dict[str, int] = {}
    for item in items:
        key = item.get("worklist_type", "UNKNOWN")
        summary[key] = summary.get(key, 0) + 1
    return summary


def sort_worklist_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sort worklist item dicts by (rank, priority, type, symbol) deterministically."""
    return sorted(
        items,
        key=lambda i: (
            i.get("rank", 9999),
            priority_rank(i.get("priority", "")),
            type_rank(i.get("worklist_type", "")),
            i.get("symbol", ""),
        ),
    )


__all__ = [
    "format_score",
    "group_worklist_by_type",
    "instrument_scope_label",
    "option_data_warning",
    "priority_badge",
    "sort_worklist_items",
    "summarize_worklist",
]
