"""Phase 23 — Rejection category and severity constants.

A small constants module so every classifier, explainer, and storage
writer agrees on the same label set. The two invariants:

* Missing option data is **never** a rejection. ``OPTION_DATA_NOT_AVAILABLE``
  resolves to ``CATEGORY_NOT_REJECTED`` and ``SEVERITY_NOT_REJECTED``.
* Bad pasted option data rejects **only** the option expression.
  ``STOCK_OK_OPTION_BAD`` resolves to ``CATEGORY_STOCK_OK_OPTION_BAD``
  and ``SEVERITY_OPTION_ONLY_REJECT`` -- the stock thesis is NOT
  recorded as a rejected stock candidate.
"""

from __future__ import annotations

# --- Rejection categories ---------------------------------------------------

CATEGORY_HARD_STOCK_REJECTION = "HARD_STOCK_REJECTION"
CATEGORY_STOCK_OK_OPTION_BAD = "STOCK_OK_OPTION_BAD"
CATEGORY_DATA_INSUFFICIENT = "DATA_INSUFFICIENT"
CATEGORY_NOT_REJECTED = "NOT_REJECTED"

ALL_CATEGORIES = frozenset(
    {
        CATEGORY_HARD_STOCK_REJECTION,
        CATEGORY_STOCK_OK_OPTION_BAD,
        CATEGORY_DATA_INSUFFICIENT,
        CATEGORY_NOT_REJECTED,
    }
)

# --- Rejection severity -----------------------------------------------------

SEVERITY_HARD_REJECT = "HARD_REJECT"
SEVERITY_OPTION_ONLY_REJECT = "OPTION_ONLY_REJECT"
SEVERITY_NOT_EVALUATED = "NOT_EVALUATED"
SEVERITY_NOT_REJECTED = "NOT_REJECTED"

# --- Rejection reason categories -------------------------------------------

REASON_CATEGORY_STOCK = "STOCK"
REASON_CATEGORY_OPTION = "OPTION"
REASON_CATEGORY_DATA = "DATA"
REASON_CATEGORY_EVENT = "EVENT"

# --- Source phases ---------------------------------------------------------

SOURCE_PHASE_HARD_FILTER = "HARD_FILTER"
SOURCE_PHASE_DATA_SUFFICIENCY = "DATA_SUFFICIENCY"
SOURCE_PHASE_OPTION_EXPRESSION = "OPTION_EXPRESSION"
SOURCE_PHASE_DECISION_TRACE = "DECISION_TRACE"


__all__ = [
    "ALL_CATEGORIES",
    "CATEGORY_DATA_INSUFFICIENT",
    "CATEGORY_HARD_STOCK_REJECTION",
    "CATEGORY_NOT_REJECTED",
    "CATEGORY_STOCK_OK_OPTION_BAD",
    "REASON_CATEGORY_DATA",
    "REASON_CATEGORY_EVENT",
    "REASON_CATEGORY_OPTION",
    "REASON_CATEGORY_STOCK",
    "SEVERITY_HARD_REJECT",
    "SEVERITY_NOT_EVALUATED",
    "SEVERITY_NOT_REJECTED",
    "SEVERITY_OPTION_ONLY_REJECT",
    "SOURCE_PHASE_DATA_SUFFICIENCY",
    "SOURCE_PHASE_DECISION_TRACE",
    "SOURCE_PHASE_HARD_FILTER",
    "SOURCE_PHASE_OPTION_EXPRESSION",
]
