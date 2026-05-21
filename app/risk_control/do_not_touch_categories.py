"""Phase 24 — Do-Not-Touch category and severity constants.

A single source of truth so the classifier, manager, explainer, memory
writer, and routes never drift on label strings.

The two invariants the constants reflect:

* Missing option data alone is **never** a freeze condition. There is
  deliberately no ``MISSING_OPTION_DATA`` category here.
* Extreme **pasted** option risk can be a freeze condition; the relevant
  categories are ``EXTREME_OPTION_VOLATILITY`` and
  ``EXTREME_OPTION_LIQUIDITY_RISK``.
"""

from __future__ import annotations

# --- Freeze categories ------------------------------------------------------

FREEZE_CATEGORY_EARNINGS_BEFORE_EXPIRATION = "EARNINGS_BEFORE_EXPIRATION"
FREEZE_CATEGORY_EXTREME_OPTION_VOLATILITY = "EXTREME_OPTION_VOLATILITY"
FREEZE_CATEGORY_EXTREME_OPTION_LIQUIDITY_RISK = "EXTREME_OPTION_LIQUIDITY_RISK"
FREEZE_CATEGORY_REPEATED_REJECTIONS = "REPEATED_REJECTIONS"
FREEZE_CATEGORY_MANUAL = "MANUAL"

ALL_FREEZE_CATEGORIES = frozenset(
    {
        FREEZE_CATEGORY_EARNINGS_BEFORE_EXPIRATION,
        FREEZE_CATEGORY_EXTREME_OPTION_VOLATILITY,
        FREEZE_CATEGORY_EXTREME_OPTION_LIQUIDITY_RISK,
        FREEZE_CATEGORY_REPEATED_REJECTIONS,
        FREEZE_CATEGORY_MANUAL,
    }
)

# --- Severities -------------------------------------------------------------

SEVERITY_HARD_FREEZE = "HARD_FREEZE"
SEVERITY_SOFT_FREEZE = "SOFT_FREEZE"

# --- Trigger sources --------------------------------------------------------

TRIGGER_AUTOMATIC = "AUTOMATIC"
TRIGGER_USER = "USER"
TRIGGER_EXPIRATION_SWEEP = "EXPIRATION_SWEEP"

# --- Source phases ----------------------------------------------------------

SOURCE_PHASE_CLASSIFIER = "DO_NOT_TOUCH_CLASSIFIER"
SOURCE_PHASE_MANUAL = "MANUAL_INPUT"
SOURCE_PHASE_EXPIRATION = "EXPIRATION_MONITOR"

# --- History event types ----------------------------------------------------

EVENT_FROZEN = "FROZEN"
EVENT_RELEASED = "RELEASED"
EVENT_RENEWED = "RENEWED"
EVENT_EXPIRED = "EXPIRED"

# --- Release condition kinds ------------------------------------------------

RELEASE_KIND_TIME = "TIME_BASED"
RELEASE_KIND_EVENT = "EVENT_BASED"
RELEASE_KIND_MANUAL = "MANUAL_ONLY"

# --- Default freeze windows (in days) ---------------------------------------

DEFAULT_FREEZE_DAYS_EARNINGS = 1   # 1 day after earnings
DEFAULT_FREEZE_DAYS_EXTREME_VOL = 7
DEFAULT_FREEZE_DAYS_EXTREME_LIQUIDITY = 7
DEFAULT_FREEZE_DAYS_REPEATED_REJECTIONS = 14
DEFAULT_FREEZE_DAYS_MANUAL = None  # indefinite by default

# --- Repeated-rejection threshold -------------------------------------------

DEFAULT_REPEATED_REJECTIONS_WINDOW_DAYS = 14
DEFAULT_REPEATED_REJECTIONS_THRESHOLD = 3


__all__ = [
    "ALL_FREEZE_CATEGORIES",
    "DEFAULT_FREEZE_DAYS_EARNINGS",
    "DEFAULT_FREEZE_DAYS_EXTREME_LIQUIDITY",
    "DEFAULT_FREEZE_DAYS_EXTREME_VOL",
    "DEFAULT_FREEZE_DAYS_MANUAL",
    "DEFAULT_FREEZE_DAYS_REPEATED_REJECTIONS",
    "DEFAULT_REPEATED_REJECTIONS_THRESHOLD",
    "DEFAULT_REPEATED_REJECTIONS_WINDOW_DAYS",
    "EVENT_EXPIRED",
    "EVENT_FROZEN",
    "EVENT_RELEASED",
    "EVENT_RENEWED",
    "FREEZE_CATEGORY_EARNINGS_BEFORE_EXPIRATION",
    "FREEZE_CATEGORY_EXTREME_OPTION_LIQUIDITY_RISK",
    "FREEZE_CATEGORY_EXTREME_OPTION_VOLATILITY",
    "FREEZE_CATEGORY_MANUAL",
    "FREEZE_CATEGORY_REPEATED_REJECTIONS",
    "RELEASE_KIND_EVENT",
    "RELEASE_KIND_MANUAL",
    "RELEASE_KIND_TIME",
    "SEVERITY_HARD_FREEZE",
    "SEVERITY_SOFT_FREEZE",
    "SOURCE_PHASE_CLASSIFIER",
    "SOURCE_PHASE_EXPIRATION",
    "SOURCE_PHASE_MANUAL",
    "TRIGGER_AUTOMATIC",
    "TRIGGER_EXPIRATION_SWEEP",
    "TRIGGER_USER",
]
