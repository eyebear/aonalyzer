"""Phase 22, step 22.10 — Manual option input action builder.

Phase 22 deliberately reuses the Phase 19
``InsufficientDataActionBuilder`` for general "what data to add"
guidance (step 22.9). This module focuses on the *option-specific*
manual-input prompt: when the user has indicated they want option
analysis but no option data is available, the action package should
tell them exactly what to paste.

Outputs:

* ``manual_option_input_needed`` -- a boolean flag for the formatter.
* A list of structured action entries the formatter can mix into
  ``action_items``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.action.option_contract_criteria_builder import OptionContractCriteria
from app.decision.decision_labels import (
    OPTION_DATA_NOT_AVAILABLE,
    STOCK_OK_OPTION_BAD,
)


@dataclass(frozen=True)
class ManualOptionInputAction:
    needed: bool
    actions: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {"needed": self.needed, "actions": list(self.actions)}


def build_manual_option_input_action(
    *,
    final_label: str,
    option_data_requested: bool,
    option_already_supplied: bool,
    criteria: OptionContractCriteria | None,
    symbol: str | None,
) -> ManualOptionInputAction:
    needed = False
    actions: list[dict[str, Any]] = []

    if final_label == OPTION_DATA_NOT_AVAILABLE:
        needed = True
        actions.append(
            _action(
                action="PASTE_MANUAL_OPTION",
                priority="HIGH",
                description=(
                    "Paste a manual option contract for this symbol. The stock "
                    "thesis is ready; only the option side is missing."
                ),
                symbol=symbol,
                criteria=criteria,
            )
        )
        return ManualOptionInputAction(needed=needed, actions=actions)

    if final_label == STOCK_OK_OPTION_BAD:
        needed = True
        actions.append(
            _action(
                action="REPASTE_MANUAL_OPTION",
                priority="MEDIUM",
                description=(
                    "Re-paste a manual option contract that meets the criteria; "
                    "the previously supplied contract failed hard filters."
                ),
                symbol=symbol,
                criteria=criteria,
            )
        )
        return ManualOptionInputAction(needed=needed, actions=actions)

    if option_data_requested and not option_already_supplied:
        needed = True
        actions.append(
            _action(
                action="PASTE_MANUAL_OPTION",
                priority="MEDIUM",
                description=(
                    "Option analysis was requested. Paste a contract matching "
                    "the option_contract_criteria to enable the option-aware path."
                ),
                symbol=symbol,
                criteria=criteria,
            )
        )

    return ManualOptionInputAction(needed=needed, actions=actions)


def _action(
    *,
    action: str,
    priority: str,
    description: str,
    symbol: str | None,
    criteria: OptionContractCriteria | None,
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "action": action,
        "priority": priority,
        "description": description,
        "symbol": symbol,
        "category": "MANUAL_OPTION_INPUT",
    }
    if criteria is not None:
        entry["option_contract_criteria"] = criteria.to_dict()
    return entry


__all__ = ["ManualOptionInputAction", "build_manual_option_input_action"]
