"""Phase 28, steps 28.4-28.14 — one-page ticker brief sections.

Pure section builders. Each returns a self-describing dict with an
``available`` flag so the dashboard can render absent data honestly instead
of inventing fallback values. No DB I/O and no decision recomputation here —
these functions only shape data the service has already assembled.
"""

from __future__ import annotations

from typing import Any

# Option-expression statuses that mean "option side was NOT evaluated".
OPTION_NOT_EVALUATED_STATUSES = frozenset(
    {"OPTION_EXPR_NOT_EVALUATED", "NOT_EVALUATED", "OPTION_DATA_NOT_AVAILABLE", ""}
)

OPTION_DATA_NOT_AVAILABLE = "OPTION_DATA_NOT_AVAILABLE"


def build_current_action_section(
    *,
    final_action_label: str,
    suggested_action_summary: str | None,
    priority_score: float | None,
    confidence_score: float | None,
    lifecycle_state: str | None,
    instrument_scope: str | None,
) -> dict[str, Any]:
    """28.5 — the final action the user should take now."""
    return {
        "section": "current_action",
        "available": True,
        "final_action_label": final_action_label,
        "suggested_action_summary": suggested_action_summary,
        "priority_score": priority_score,
        "confidence_score": confidence_score,
        "lifecycle_state": lifecycle_state,
        "instrument_scope": instrument_scope,
    }


def build_stock_thesis_section(stock_thesis: dict[str, Any] | None) -> dict[str, Any]:
    """28.6 — the technical stock thesis."""
    if not stock_thesis:
        return {
            "section": "stock_thesis",
            "available": False,
            "detail": "No stock thesis was produced for this symbol.",
        }
    return {
        "section": "stock_thesis",
        "available": True,
        "thesis_label": stock_thesis.get("thesis_label"),
        "rationale": stock_thesis.get("rationale", []),
        "inside_entry_zone": stock_thesis.get("inside_entry_zone"),
    }


def build_option_expression_section(
    *,
    option_expression: dict[str, Any] | None,
    has_manual_snapshot: bool,
    option_contract_criteria: dict[str, Any] | None,
) -> dict[str, Any]:
    """28.7 — option status if available; explicit empty state otherwise.

    The empty state states plainly that the Option Expression status is
    OPTION_DATA_NOT_AVAILABLE, that no manual option snapshot is available,
    and that the stock thesis was evaluated without option contract analysis.
    """
    expression_label = (option_expression or {}).get("expression_label", "")
    option_evaluated = (
        has_manual_snapshot
        and expression_label not in OPTION_NOT_EVALUATED_STATUSES
    )

    if not option_evaluated:
        return {
            "section": "option_expression",
            "available": False,
            "option_expression_status": OPTION_DATA_NOT_AVAILABLE,
            "has_manual_option_snapshot": has_manual_snapshot,
            "detail": (
                "Option Expression status is OPTION_DATA_NOT_AVAILABLE. No "
                "manual option snapshot was available, so the stock thesis was "
                "evaluated without option contract analysis. Stock-only "
                "research can still proceed."
            ),
            "option_contract_criteria": option_contract_criteria,
        }

    return {
        "section": "option_expression",
        "available": True,
        "option_expression_status": expression_label,
        "has_manual_option_snapshot": True,
        "blocking_labels": (option_expression or {}).get("blocking_labels", []),
        "rationale": (option_expression or {}).get("rationale", []),
        "option_contract_criteria": option_contract_criteria,
    }


def build_manual_option_reminder_section(
    *,
    manual_option_input_needed: bool,
    has_manual_snapshot: bool,
    missing_fields: list[str] | None,
    option_contract_criteria: dict[str, Any] | None,
) -> dict[str, Any]:
    """28.8 — tell the user exactly what option data is missing."""
    if not manual_option_input_needed:
        return {
            "section": "manual_option_reminder",
            "available": False,
            "detail": "No manual option input is required for this symbol right now.",
        }
    return {
        "section": "manual_option_reminder",
        "available": True,
        "has_manual_option_snapshot": has_manual_snapshot,
        "missing_fields": list(missing_fields or []),
        "expected_fields": [
            "symbol",
            "expiration",
            "strike",
            "call/put",
            "bid",
            "ask",
            "last",
            "implied_volatility",
            "delta",
            "gamma",
            "theta",
            "vega",
            "volume",
            "open_interest",
        ],
        "option_contract_criteria": option_contract_criteria,
        "detail": (
            "Paste a manual option contract from your chosen website or broker "
            "to enable option suitability analysis. Missing fields are shown "
            "honestly and are never invented."
        ),
    }


def build_earnings_iv_section(
    *,
    earnings: dict[str, Any] | None,
    iv: dict[str, Any] | None,
) -> dict[str, Any]:
    """28.9 — earnings + IV risk. Missing IV is reported, never faked."""
    section: dict[str, Any] = {
        "section": "earnings_iv",
        "available": bool(earnings or iv),
    }
    if earnings:
        section["earnings"] = {
            "available": True,
            "next_earnings_datetime_utc": earnings.get("next_earnings_datetime_utc"),
            "days_to_earnings": earnings.get("days_to_earnings"),
            "earnings_within_window": earnings.get("earnings_within_window"),
            "earnings_before_expiration": earnings.get("earnings_before_expiration"),
            "risk_label": earnings.get("risk_label"),
        }
    else:
        section["earnings"] = {
            "available": False,
            "detail": "No earnings risk snapshot is available.",
        }
    if iv:
        section["iv"] = {
            "available": True,
            "current_iv": iv.get("current_iv"),
            "iv_rank": iv.get("iv_rank"),
            "iv_percentile": iv.get("iv_percentile"),
            "risk_label": iv.get("risk_label"),
        }
    else:
        section["iv"] = {
            "available": False,
            "detail": "IV data is not available; IV risk is shown as unavailable, not low.",
        }
    return section


def build_news_events_section(events: list[dict[str, Any]] | None) -> dict[str, Any]:
    """28.10 — relevant recent events."""
    events = events or []
    return {
        "section": "news_events",
        "available": bool(events),
        "events": events,
        "detail": None if events else "No recent events recorded for this symbol.",
    }


def build_memory_section(similar_cases: list[dict[str, Any]] | None) -> dict[str, Any]:
    """28.11 — memory / similar past cases.

    Case + vector memory arrive in Phases 41-42; until cases exist this section
    honestly reports that no similar cases are stored yet.
    """
    similar_cases = similar_cases or []
    return {
        "section": "memory_similar_cases",
        "available": bool(similar_cases),
        "similar_cases": similar_cases,
        "detail": None
        if similar_cases
        else "No similar historical cases are stored for this symbol yet.",
    }


def build_decision_trace_section(trace: list[dict[str, Any]] | None) -> dict[str, Any]:
    """28.12 — explainable decision trace."""
    trace = trace or []
    return {
        "section": "decision_trace",
        "available": bool(trace),
        "trace": trace,
    }


def build_confidence_section(
    *,
    confidence_score: float | None,
    breakdown: dict[str, Any] | None,
) -> dict[str, Any]:
    """28.13 — confidence breakdown."""
    return {
        "section": "confidence_breakdown",
        "available": breakdown is not None,
        "confidence_score": confidence_score,
        "breakdown": breakdown or {},
    }


def build_version_section(version_stamp: dict[str, Any] | None) -> dict[str, Any]:
    """28.14 — version stamp."""
    version_stamp = version_stamp or {}
    return {
        "section": "version_stamp",
        "available": bool(version_stamp),
        "version_stamp": version_stamp,
    }


__all__ = [
    "OPTION_DATA_NOT_AVAILABLE",
    "OPTION_NOT_EVALUATED_STATUSES",
    "build_confidence_section",
    "build_current_action_section",
    "build_decision_trace_section",
    "build_earnings_iv_section",
    "build_manual_option_reminder_section",
    "build_memory_section",
    "build_news_events_section",
    "build_option_expression_section",
    "build_stock_thesis_section",
    "build_version_section",
]
