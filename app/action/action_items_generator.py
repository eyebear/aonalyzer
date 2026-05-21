"""Phase 22, step 22.11 — Action items generator.

Assembles the concrete next steps a user should take, combining:

* Phase 19 ``InsufficientDataActionBuilder`` output (step 22.9, reused),
* The Phase 22 manual-option-input prompt (step 22.10),
* Lifecycle-state-driven suggestions (e.g. "open research note",
  "log decision in dashboard").

Returns a deduplicated list ordered by priority (HIGH -> MEDIUM -> LOW).
"""

from __future__ import annotations

from typing import Any

from app.action.action_labels import (
    LIFECYCLE_AWAITING_OPTION_DATA,
    LIFECYCLE_INSUFFICIENT_DATA,
    LIFECYCLE_READY_FOR_RESEARCH,
    LIFECYCLE_REJECTED,
    LIFECYCLE_WAITING_FOR_ENTRY,
    LIFECYCLE_WATCHING,
)
from app.action.manual_option_input_action_builder import ManualOptionInputAction
from app.data_quality.data_sufficiency_gate import GateDecision as SufficiencyDecision
from app.data_quality.insufficient_data_action_builder import (
    InsufficientDataActionBuilder,
)

_PRIORITY_RANK = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}


def generate_action_items(
    *,
    sufficiency: SufficiencyDecision,
    manual_option_input: ManualOptionInputAction,
    lifecycle_state: str,
    symbol: str | None,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []

    # ----- Sufficiency-driven data fixes (step 22.9 reuse) ---------------
    builder = InsufficientDataActionBuilder()
    items.extend(
        builder.build_actions(
            blocking_labels=list(sufficiency.blocking_labels or []),
            non_blocking_labels=list(sufficiency.non_blocking_labels or []),
            confidence_reducers=list(sufficiency.confidence_reducers or []),
            option_status=sufficiency.option_status,
            symbol=symbol,
        )
    )

    # ----- Manual option input (step 22.10) -------------------------------
    items.extend(manual_option_input.actions)

    # ----- Lifecycle-state driven suggestions ----------------------------
    items.extend(_lifecycle_items(lifecycle_state=lifecycle_state, symbol=symbol))

    return _dedupe_and_sort(items)


def _lifecycle_items(*, lifecycle_state: str, symbol: str | None) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []

    if lifecycle_state == LIFECYCLE_READY_FOR_RESEARCH:
        items.append(
            {
                "action": "OPEN_RESEARCH_NOTE",
                "priority": "MEDIUM",
                "description": (
                    f"Open a research note for {symbol or 'the candidate'} so "
                    "the entry, invalidation, and review triggers are recorded."
                ),
                "symbol": symbol,
                "category": "RESEARCH_WORKFLOW",
            }
        )

    if lifecycle_state == LIFECYCLE_WATCHING:
        items.append(
            {
                "action": "SCHEDULE_WATCH_REVIEW",
                "priority": "MEDIUM",
                "description": (
                    "Schedule a watch review after the next market-data refresh "
                    "and re-evaluate the active warnings."
                ),
                "symbol": symbol,
                "category": "RESEARCH_WORKFLOW",
            }
        )

    if lifecycle_state == LIFECYCLE_WAITING_FOR_ENTRY:
        items.append(
            {
                "action": "SET_PRICE_ALERT",
                "priority": "MEDIUM",
                "description": (
                    "Set a price alert at the entry zone boundary so you are "
                    "notified when the setup becomes actionable."
                ),
                "symbol": symbol,
                "category": "RESEARCH_WORKFLOW",
            }
        )

    if lifecycle_state == LIFECYCLE_AWAITING_OPTION_DATA:
        items.append(
            {
                "action": "WAIT_FOR_OPTION_DATA",
                "priority": "MEDIUM",
                "description": (
                    "Stock thesis is ready; hold off on the option-aware "
                    "decision until a matching contract is pasted."
                ),
                "symbol": symbol,
                "category": "RESEARCH_WORKFLOW",
            }
        )

    if lifecycle_state == LIFECYCLE_INSUFFICIENT_DATA:
        items.append(
            {
                "action": "RUN_REFRESH_ALL",
                "priority": "HIGH",
                "description": (
                    "Run the full data refresh; not enough price history exists "
                    "to evaluate this symbol."
                ),
                "symbol": symbol,
                "category": "DATA_FIX",
            }
        )

    if lifecycle_state == LIFECYCLE_REJECTED:
        items.append(
            {
                "action": "LOG_REJECTION_REASON",
                "priority": "LOW",
                "description": (
                    "Log the rejection rationale into the rejected-but-interesting "
                    "workflow for future learning."
                ),
                "symbol": symbol,
                "category": "RESEARCH_WORKFLOW",
            }
        )

    return items


def _dedupe_and_sort(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str | None]] = set()
    deduped: list[dict[str, Any]] = []
    for item in items:
        key = (item.get("action", ""), item.get("symbol"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    deduped.sort(key=lambda x: _PRIORITY_RANK.get(x.get("priority", "LOW"), 2))
    return deduped


__all__ = ["generate_action_items"]
