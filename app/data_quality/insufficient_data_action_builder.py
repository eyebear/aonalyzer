"""Phase 19, step 19.10 — Insufficient-data action builder.

A small, scoped helper that maps Phase 19 data-sufficiency labels to a
short, practical next-step suggestion (e.g. "refresh market data",
"paste a manual option contract", "refresh earnings calendar").

This is **not** the future generic action-suggestion system. The
suggestions returned here are intentionally fixed strings keyed off the
sufficiency label, with a stable JSON shape that later phases can
extend without changing the gate.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.data_quality.data_sufficiency_labels import DataSufficiencyLabel

# --- Action category constants ----------------------------------------------

ACTION_REFRESH_MARKET_DATA = "REFRESH_MARKET_DATA"
ACTION_RUN_STOCK_SETUP_DETECTION = "RUN_STOCK_SETUP_DETECTION"
ACTION_PASTE_MANUAL_OPTION = "PASTE_MANUAL_OPTION"
ACTION_REPASTE_MANUAL_OPTION = "REPASTE_MANUAL_OPTION"
ACTION_REFRESH_NEWS = "REFRESH_NEWS"
ACTION_REFRESH_IV_RISK = "REFRESH_IV_RISK"
ACTION_REFRESH_EARNINGS = "REFRESH_EARNINGS"
ACTION_ADD_MEMORY_LATER = "ADD_MEMORY_LATER"


@dataclass(frozen=True)
class _ActionSpec:
    action: str
    description: str


_LABEL_TO_ACTION: dict[str, _ActionSpec] = {
    DataSufficiencyLabel.INSUFFICIENT_PRICE_HISTORY.value: _ActionSpec(
        action=ACTION_REFRESH_MARKET_DATA,
        description=(
            "Run the market-data refresh so this symbol has enough daily "
            "price rows for swing and indicator math."
        ),
    ),
    DataSufficiencyLabel.INSUFFICIENT_STOCK_SETUP_DATA.value: _ActionSpec(
        action=ACTION_RUN_STOCK_SETUP_DETECTION,
        description=(
            "Re-run stock setup detection after the next market-data "
            "refresh; recent OHLC rows look insufficient to derive "
            "support, resistance, target, and stop levels."
        ),
    ),
    # Legacy spelling — present as a key so callers passing the old label
    # still get a suggestion. The gate normalizes to the Phase 19 spelling
    # before calling this builder, but defensive coverage doesn't hurt.
    DataSufficiencyLabel.INSUFFICIENT_SETUP_DATA.value: _ActionSpec(
        action=ACTION_RUN_STOCK_SETUP_DETECTION,
        description=(
            "Re-run stock setup detection after the next market-data "
            "refresh; recent OHLC rows look insufficient to derive "
            "support, resistance, target, and stop levels."
        ),
    ),
    DataSufficiencyLabel.OPTION_DATA_NOT_AVAILABLE.value: _ActionSpec(
        action=ACTION_PASTE_MANUAL_OPTION,
        description=(
            "Paste a manual option contract for this symbol to enable "
            "option suitability analysis. Stock-only analysis is "
            "unaffected by missing option data."
        ),
    ),
    DataSufficiencyLabel.INSUFFICIENT_OPTION_DATA.value: _ActionSpec(
        action=ACTION_REPASTE_MANUAL_OPTION,
        description=(
            "Re-paste the option contract with bid, ask, open interest, "
            "and implied volatility filled in; option suitability cannot "
            "run on the current snapshot."
        ),
    ),
    DataSufficiencyLabel.INSUFFICIENT_NEWS_DATA.value: _ActionSpec(
        action=ACTION_REFRESH_NEWS,
        description=(
            "Run the news refresh so recent headlines for this symbol "
            "are stored and event analysis has context."
        ),
    ),
    DataSufficiencyLabel.INSUFFICIENT_IV_DATA.value: _ActionSpec(
        action=ACTION_REFRESH_IV_RISK,
        description=(
            "Run the IV risk refresh and, if possible, backfill IV "
            "history so IV rank and percentile can be computed."
        ),
    ),
    DataSufficiencyLabel.INSUFFICIENT_IV_HISTORY.value: _ActionSpec(
        action=ACTION_REFRESH_IV_RISK,
        description=(
            "Backfill IV history for this symbol; the gate cannot rank "
            "current IV without sufficient historical rows."
        ),
    ),
    DataSufficiencyLabel.INSUFFICIENT_EARNINGS_DATA.value: _ActionSpec(
        action=ACTION_REFRESH_EARNINGS,
        description=(
            "Run the earnings calendar refresh so upcoming earnings "
            "risk windows can be evaluated for this symbol."
        ),
    ),
    DataSufficiencyLabel.EARNINGS_DATA_NOT_AVAILABLE.value: _ActionSpec(
        action=ACTION_REFRESH_EARNINGS,
        description=(
            "No earnings calendar rows exist for this symbol yet. Run "
            "the earnings refresh once the next report date is known."
        ),
    ),
    DataSufficiencyLabel.INSUFFICIENT_MEMORY_DATA.value: _ActionSpec(
        action=ACTION_ADD_MEMORY_LATER,
        description=(
            "Memory store has too few similar records to influence "
            "confidence; this will improve as more analyses and "
            "outcomes are recorded in later phases."
        ),
    ),
}


class InsufficientDataActionBuilder:
    """Build a list of structured action suggestions from gate labels."""

    def build_actions(
        self,
        blocking_labels: list[str],
        non_blocking_labels: list[str],
        confidence_reducers: list[str],
        option_status: str,
        symbol: str | None = None,
    ) -> list[dict[str, Any]]:
        suggestions: list[dict[str, Any]] = []
        seen: set[str] = set()

        for label in blocking_labels:
            entry = self._make_entry(label=label, priority="HIGH", symbol=symbol)
            if entry is not None and entry["action"] not in seen:
                seen.add(entry["action"])
                suggestions.append(entry)

        for label in non_blocking_labels:
            entry = self._make_entry(label=label, priority="MEDIUM", symbol=symbol)
            if entry is not None and entry["action"] not in seen:
                seen.add(entry["action"])
                suggestions.append(entry)

        for label in confidence_reducers:
            entry = self._make_entry(label=label, priority="LOW", symbol=symbol)
            if entry is not None and entry["action"] not in seen:
                seen.add(entry["action"])
                suggestions.append(entry)

        # ``OPTION_OK`` and the gate-internal ``OPTION_ANALYSIS_NOT_REQUESTED``
        # never produce an action.
        return suggestions

    @staticmethod
    def _make_entry(
        label: str,
        priority: str,
        symbol: str | None,
    ) -> dict[str, Any] | None:
        spec = _LABEL_TO_ACTION.get(label)
        if spec is None:
            return None
        return {
            "label": label,
            "action": spec.action,
            "description": spec.description,
            "priority": priority,
            "symbol": symbol,
        }


__all__ = [
    "ACTION_ADD_MEMORY_LATER",
    "ACTION_PASTE_MANUAL_OPTION",
    "ACTION_REFRESH_EARNINGS",
    "ACTION_REFRESH_IV_RISK",
    "ACTION_REFRESH_MARKET_DATA",
    "ACTION_REFRESH_NEWS",
    "ACTION_REPASTE_MANUAL_OPTION",
    "ACTION_RUN_STOCK_SETUP_DETECTION",
    "InsufficientDataActionBuilder",
]
