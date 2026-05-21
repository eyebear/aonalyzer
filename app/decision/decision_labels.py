"""Phase 21 — central label constants for the decision intelligence layer.

Two layers of labels exist:

* **Internal labels** produced by the sub-decisions (e.g. ``READY_TO_RESEARCH``
  by ``stock_thesis_decision``). These are NOT the final user-facing labels.
* **Final action labels** produced by ``action_label_classifier``. These are
  the eight strings exposed in the API and dashboard.

The mapping is deliberately one-way: every final label is produced by
combining a stock-thesis internal label with an instrument-scope value,
and the mapping is documented in ``action_label_classifier``.
"""

from __future__ import annotations

# --- Final action labels (the eight user-facing outcomes) -------------------

READY_TO_RESEARCH_STOCK_ONLY = "READY_TO_RESEARCH_STOCK_ONLY"
WATCH_STOCK_ONLY = "WATCH_STOCK_ONLY"
WAIT_FOR_ENTRY_STOCK_ONLY = "WAIT_FOR_ENTRY_STOCK_ONLY"
READY_TO_RESEARCH_WITH_OPTION = "READY_TO_RESEARCH_WITH_OPTION"
STOCK_OK_OPTION_BAD = "STOCK_OK_OPTION_BAD"
OPTION_DATA_NOT_AVAILABLE = "OPTION_DATA_NOT_AVAILABLE"
NO_TRADE = "NO_TRADE"
INSUFFICIENT_PRICE_HISTORY = "INSUFFICIENT_PRICE_HISTORY"

FINAL_LABELS = frozenset(
    {
        READY_TO_RESEARCH_STOCK_ONLY,
        WATCH_STOCK_ONLY,
        WAIT_FOR_ENTRY_STOCK_ONLY,
        READY_TO_RESEARCH_WITH_OPTION,
        STOCK_OK_OPTION_BAD,
        OPTION_DATA_NOT_AVAILABLE,
        NO_TRADE,
        INSUFFICIENT_PRICE_HISTORY,
    }
)

# --- Stock thesis internal labels ------------------------------------------

THESIS_INSUFFICIENT_PRICE_HISTORY = "INSUFFICIENT_PRICE_HISTORY"
THESIS_NO_TRADE = "NO_TRADE"
THESIS_WAIT_FOR_ENTRY = "WAIT_FOR_ENTRY"
THESIS_WATCH = "WATCH"
THESIS_READY_TO_RESEARCH = "READY_TO_RESEARCH"

# --- Option expression internal labels --------------------------------------

OPTION_EXPR_OK = "OPTION_OK"
OPTION_EXPR_BAD = "OPTION_BAD"
OPTION_EXPR_NOT_EVALUATED = "OPTION_NOT_EVALUATED"

# --- Instrument scope labels ------------------------------------------------

SCOPE_STOCK_ONLY = "STOCK_ONLY"
SCOPE_OPTION_AVAILABLE = "OPTION_AVAILABLE"
SCOPE_OPTION_REJECTED = "OPTION_REJECTED"

# --- Risk levels -----------------------------------------------------------

RISK_LOW = "LOW"
RISK_MEDIUM = "MEDIUM"
RISK_HIGH = "HIGH"
RISK_UNKNOWN = "UNKNOWN"

# --- Checklist statuses -----------------------------------------------------

CHECK_PASS = "PASS"
CHECK_WARNING = "WARNING"
CHECK_FAIL = "FAIL"
CHECK_SKIPPED = "SKIPPED"


__all__ = [
    "CHECK_FAIL",
    "CHECK_PASS",
    "CHECK_SKIPPED",
    "CHECK_WARNING",
    "FINAL_LABELS",
    "INSUFFICIENT_PRICE_HISTORY",
    "NO_TRADE",
    "OPTION_DATA_NOT_AVAILABLE",
    "OPTION_EXPR_BAD",
    "OPTION_EXPR_NOT_EVALUATED",
    "OPTION_EXPR_OK",
    "READY_TO_RESEARCH_STOCK_ONLY",
    "READY_TO_RESEARCH_WITH_OPTION",
    "RISK_HIGH",
    "RISK_LOW",
    "RISK_MEDIUM",
    "RISK_UNKNOWN",
    "SCOPE_OPTION_AVAILABLE",
    "SCOPE_OPTION_REJECTED",
    "SCOPE_STOCK_ONLY",
    "STOCK_OK_OPTION_BAD",
    "THESIS_INSUFFICIENT_PRICE_HISTORY",
    "THESIS_NO_TRADE",
    "THESIS_READY_TO_RESEARCH",
    "THESIS_WAIT_FOR_ENTRY",
    "THESIS_WATCH",
    "WAIT_FOR_ENTRY_STOCK_ONLY",
    "WATCH_STOCK_ONLY",
]
