"""Phase 26, steps 26.4 - 26.9 — Per-trigger evaluators.

Each evaluator is a small pure function that consumes a single
``EvaluatorInputs`` payload and returns either ``None`` (no fire) or
an ``EvaluatorResult`` describing the fire reason. The engine wires
the evaluators to the persistent ``ReviewTrigger`` rows.

The six evaluators:

* ``evaluate_price_entered_zone``         (step 26.4)
* ``evaluate_manual_option_input``        (step 26.5 — the NEW
  ``RECHECK_AFTER_MANUAL_OPTION_INPUT`` trigger)
* ``evaluate_iv_cooled_down``             (step 26.6)
* ``evaluate_earnings_aftermath``         (step 26.7)
* ``evaluate_new_important_event``        (step 26.8)
* ``evaluate_data_refresh_restored``      (step 26.9)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.review.review_trigger_types import (
    DEFAULT_TRIGGER_PRIORITY,
    TRIGGER_DATA_REFRESH_RESTORED,
    TRIGGER_EARNINGS_AFTERMATH,
    TRIGGER_IV_COOLED_DOWN,
    TRIGGER_NEW_IMPORTANT_EVENT,
    TRIGGER_PRICE_ENTERED_ZONE,
    TRIGGER_RECHECK_AFTER_MANUAL_OPTION_INPUT,
)


@dataclass(frozen=True)
class EvaluatorInputs:
    """All inputs an evaluator may need. Unused fields stay ``None``."""

    symbol: str
    lifecycle_state: str | None = None

    # Price / setup
    current_close: float | None = None
    entry_zone_low: float | None = None
    entry_zone_high: float | None = None

    # Manual option input
    has_manual_option_snapshot: bool = False
    manual_option_snapshot_created_at: datetime | None = None
    trigger_armed_at: datetime | None = None

    # IV
    latest_iv_percent: float | None = None
    iv_cool_threshold_percent: float | None = None

    # Earnings
    next_earnings_datetime_utc: datetime | None = None
    last_earnings_datetime_utc: datetime | None = None
    earnings_aftermath_window_hours: int = 12

    # News / events
    high_importance_event_count_since_last_eval: int = 0
    last_high_importance_event_at: datetime | None = None

    # Data refresh
    previously_insufficient: bool = False
    now_sufficient: bool = False
    insufficient_labels: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class EvaluatorResult:
    trigger_type: str
    priority: str
    summary: str
    review_reason_label: str
    context: dict[str, Any] = field(default_factory=dict)
    due_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "trigger_type": self.trigger_type,
            "priority": self.priority,
            "summary": self.summary,
            "review_reason_label": self.review_reason_label,
            "context": dict(self.context),
            "due_at": self.due_at.isoformat() if self.due_at is not None else None,
        }


def _priority(trigger_type: str) -> str:
    return DEFAULT_TRIGGER_PRIORITY.get(trigger_type, "MEDIUM")


# --- 26.4 ------------------------------------------------------------------


def evaluate_price_entered_zone(inputs: EvaluatorInputs) -> EvaluatorResult | None:
    """Fires when the current close is inside the configured entry zone."""
    if inputs.current_close is None:
        return None
    if inputs.entry_zone_low is None or inputs.entry_zone_high is None:
        return None
    low = min(inputs.entry_zone_low, inputs.entry_zone_high)
    high = max(inputs.entry_zone_low, inputs.entry_zone_high)
    if not (low <= inputs.current_close <= high):
        return None
    return EvaluatorResult(
        trigger_type=TRIGGER_PRICE_ENTERED_ZONE,
        priority=_priority(TRIGGER_PRICE_ENTERED_ZONE),
        review_reason_label="PRICE_INSIDE_ENTRY_ZONE",
        summary=(
            f"{inputs.symbol} is inside the entry zone "
            f"[{low:.2f}, {high:.2f}] at {inputs.current_close:.2f}."
        ),
        context={
            "current_close": inputs.current_close,
            "entry_zone_low": low,
            "entry_zone_high": high,
        },
    )


# --- 26.5 (the NEW RECHECK_AFTER_MANUAL_OPTION_INPUT) ---------------------


def evaluate_manual_option_input(
    inputs: EvaluatorInputs,
) -> EvaluatorResult | None:
    """Fires when a manual option snapshot exists for the symbol *after*
    the trigger was armed."""
    if not inputs.has_manual_option_snapshot:
        return None
    snap_at = inputs.manual_option_snapshot_created_at
    armed_at = inputs.trigger_armed_at
    if snap_at is None:
        return None
    if armed_at is not None and snap_at < armed_at:
        return None
    return EvaluatorResult(
        trigger_type=TRIGGER_RECHECK_AFTER_MANUAL_OPTION_INPUT,
        priority=_priority(TRIGGER_RECHECK_AFTER_MANUAL_OPTION_INPUT),
        review_reason_label="MANUAL_OPTION_INPUT_RECEIVED",
        summary=(
            f"{inputs.symbol} has a new manual option snapshot pasted at "
            f"{snap_at.isoformat()}; re-run the option-aware analysis."
        ),
        context={
            "snapshot_created_at": snap_at.isoformat(),
            "trigger_armed_at": armed_at.isoformat() if armed_at else None,
        },
    )


# --- 26.6 ------------------------------------------------------------------


def evaluate_iv_cooled_down(inputs: EvaluatorInputs) -> EvaluatorResult | None:
    """Fires when the latest IV (when available) is below the cool-down
    threshold. If no IV data is available the evaluator does not fire --
    Phase 19/24 invariants preserved: missing IV data is never used to
    flip a state on its own."""
    if inputs.latest_iv_percent is None:
        return None
    threshold = inputs.iv_cool_threshold_percent
    if threshold is None:
        return None
    if inputs.latest_iv_percent >= threshold:
        return None
    return EvaluatorResult(
        trigger_type=TRIGGER_IV_COOLED_DOWN,
        priority=_priority(TRIGGER_IV_COOLED_DOWN),
        review_reason_label="IV_COOLED_DOWN",
        summary=(
            f"IV on {inputs.symbol} has fallen to {inputs.latest_iv_percent:.1f}% "
            f"(< cool-down threshold {threshold:.1f}%)."
        ),
        context={
            "latest_iv_percent": inputs.latest_iv_percent,
            "threshold_percent": threshold,
        },
    )


# --- 26.7 ------------------------------------------------------------------


def evaluate_earnings_aftermath(
    inputs: EvaluatorInputs,
    *,
    now: datetime | None = None,
) -> EvaluatorResult | None:
    """Fires once the earnings event has fully passed (i.e. ``now`` is at
    least ``earnings_aftermath_window_hours`` after the event)."""
    now = now or datetime.now(timezone.utc)
    earnings_dt = inputs.last_earnings_datetime_utc or inputs.next_earnings_datetime_utc
    if earnings_dt is None:
        return None
    aftermath_threshold = earnings_dt.replace()
    if (now - aftermath_threshold).total_seconds() < (
        inputs.earnings_aftermath_window_hours * 3600
    ):
        return None
    return EvaluatorResult(
        trigger_type=TRIGGER_EARNINGS_AFTERMATH,
        priority=_priority(TRIGGER_EARNINGS_AFTERMATH),
        review_reason_label="EARNINGS_EVENT_CLEARED",
        summary=(
            f"Earnings event for {inputs.symbol} cleared at "
            f"{earnings_dt.isoformat()}; re-evaluate the candidate now that "
            "the event risk has passed."
        ),
        context={
            "earnings_datetime_utc": earnings_dt.isoformat(),
            "aftermath_window_hours": inputs.earnings_aftermath_window_hours,
        },
    )


# --- 26.8 ------------------------------------------------------------------


def evaluate_new_important_event(
    inputs: EvaluatorInputs,
) -> EvaluatorResult | None:
    """Fires when one or more new HIGH-importance events have appeared
    since the trigger was last armed / evaluated."""
    if inputs.high_importance_event_count_since_last_eval <= 0:
        return None
    return EvaluatorResult(
        trigger_type=TRIGGER_NEW_IMPORTANT_EVENT,
        priority=_priority(TRIGGER_NEW_IMPORTANT_EVENT),
        review_reason_label="NEW_HIGH_IMPORTANCE_EVENT",
        summary=(
            f"{inputs.high_importance_event_count_since_last_eval} new "
            f"high-importance event(s) recorded for {inputs.symbol}."
        ),
        context={
            "high_importance_event_count": (
                inputs.high_importance_event_count_since_last_eval
            ),
            "last_high_importance_event_at": (
                inputs.last_high_importance_event_at.isoformat()
                if inputs.last_high_importance_event_at is not None
                else None
            ),
        },
    )


# --- 26.9 ------------------------------------------------------------------


def evaluate_data_refresh_restored(
    inputs: EvaluatorInputs,
) -> EvaluatorResult | None:
    """Fires when a symbol that was previously short on required data is
    now sufficient (e.g. enough price rows, IV history, earnings)."""
    if not inputs.previously_insufficient:
        return None
    if not inputs.now_sufficient:
        return None
    return EvaluatorResult(
        trigger_type=TRIGGER_DATA_REFRESH_RESTORED,
        priority=_priority(TRIGGER_DATA_REFRESH_RESTORED),
        review_reason_label="DATA_REFRESH_RESTORED",
        summary=(
            f"Previously insufficient data for {inputs.symbol} is now "
            f"sufficient ({', '.join(inputs.insufficient_labels) or 'all categories'})."
        ),
        context={
            "previously_insufficient": True,
            "now_sufficient": True,
            "resolved_labels": list(inputs.insufficient_labels),
        },
    )


__all__ = [
    "EvaluatorInputs",
    "EvaluatorResult",
    "evaluate_data_refresh_restored",
    "evaluate_earnings_aftermath",
    "evaluate_iv_cooled_down",
    "evaluate_manual_option_input",
    "evaluate_new_important_event",
    "evaluate_price_entered_zone",
]
