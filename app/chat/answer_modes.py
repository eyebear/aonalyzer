"""Phase 37, step 37.5 — answer mode router + mode metadata.

Answer modes shape the *format* of the response only. They never bypass system
rules (data sufficiency, hard filters, the deterministic final label). The
router resolves an arbitrary requested mode to a known mode, defaulting to
EXPLAIN.
"""

from __future__ import annotations

MODE_EXPLAIN = "EXPLAIN"
MODE_ACTION_PLAN = "ACTION_PLAN"
MODE_RISK_REVIEW = "RISK_REVIEW"
MODE_DECISION_TRACE = "DECISION_TRACE"
MODE_COUNTERARGUMENT = "COUNTERARGUMENT"
MODE_SIMILAR_CASE = "SIMILAR_CASE"
MODE_OPTION_TEXT_READER = "OPTION_TEXT_READER"

ALL_MODES = (
    MODE_EXPLAIN,
    MODE_ACTION_PLAN,
    MODE_RISK_REVIEW,
    MODE_DECISION_TRACE,
    MODE_COUNTERARGUMENT,
    MODE_SIMILAR_CASE,
    MODE_OPTION_TEXT_READER,
)

DEFAULT_MODE = MODE_EXPLAIN

# Per-mode instruction appended to the system prompt to shape output format.
MODE_INSTRUCTIONS: dict[str, str] = {
    MODE_EXPLAIN: "Explain the system's decision for the symbol in plain language.",
    MODE_ACTION_PLAN: "Produce a concrete, ordered action plan from the decision.",
    MODE_RISK_REVIEW: "Review the key risks (event, IV, earnings, memory, liquidity).",
    MODE_DECISION_TRACE: "Walk through the decision trace step by step.",
    MODE_COUNTERARGUMENT: "Argue the opposing view to the system's decision.",
    MODE_SIMILAR_CASE: "Summarize similar past cases and what they imply.",
    MODE_OPTION_TEXT_READER: (
        "Read the pasted option text and explain it. State which fields are "
        "present and which are missing. NEVER invent missing option values."
    ),
}


def route_mode(requested: str | None) -> str:
    """Resolve a requested mode string to a known mode (default EXPLAIN)."""
    if requested is None:
        return DEFAULT_MODE
    candidate = str(requested).strip().upper()
    return candidate if candidate in ALL_MODES else DEFAULT_MODE


def mode_instruction(mode: str) -> str:
    return MODE_INSTRUCTIONS.get(mode, MODE_INSTRUCTIONS[DEFAULT_MODE])


__all__ = [
    "ALL_MODES",
    "DEFAULT_MODE",
    "MODE_ACTION_PLAN",
    "MODE_COUNTERARGUMENT",
    "MODE_DECISION_TRACE",
    "MODE_EXPLAIN",
    "MODE_INSTRUCTIONS",
    "MODE_OPTION_TEXT_READER",
    "MODE_RISK_REVIEW",
    "MODE_SIMILAR_CASE",
    "mode_instruction",
    "route_mode",
]
