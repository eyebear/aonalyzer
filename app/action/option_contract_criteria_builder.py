"""Phase 22, step 22.3 — Option contract criteria builder.

Produces ``option_contract_criteria`` only when the user has indicated
they want option analysis (either by supplying option data or by
explicitly requesting it). When option data is irrelevant to the
current opportunity, returns ``None`` so the formatter can drop the
field cleanly -- never invents synthetic criteria.

The criteria are read from the active strategy profile and the global
option-suitability settings, so the dashboard surface what the user
*should* paste rather than re-deriving thresholds.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.config import AppSettings, get_settings
from app.decision.decision_labels import (
    OPTION_DATA_NOT_AVAILABLE,
    READY_TO_RESEARCH_WITH_OPTION,
    STOCK_OK_OPTION_BAD,
)
from app.profiles.profile_models import StrategyProfile


@dataclass(frozen=True)
class OptionContractCriteria:
    direction_hint: str | None  # CALL / PUT / null when unclear
    dte_min: int
    dte_max: int
    premium_min_usd: float
    premium_max_usd: float
    max_spread_percent: float
    min_open_interest: int
    iv_warning_threshold: float
    iv_reject_threshold: float
    minimum_target_breakeven_margin_percent: float
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "direction_hint": self.direction_hint,
            "dte_min": self.dte_min,
            "dte_max": self.dte_max,
            "premium_min_usd": self.premium_min_usd,
            "premium_max_usd": self.premium_max_usd,
            "max_spread_percent": self.max_spread_percent,
            "min_open_interest": self.min_open_interest,
            "iv_warning_threshold": self.iv_warning_threshold,
            "iv_reject_threshold": self.iv_reject_threshold,
            "minimum_target_breakeven_margin_percent": (
                self.minimum_target_breakeven_margin_percent
            ),
            "notes": list(self.notes),
        }


def is_option_relevant(
    final_label: str,
    *,
    option_data_requested: bool,
    option_already_supplied: bool,
) -> bool:
    """Decide whether option criteria belong on the final package."""
    if option_already_supplied:
        return True
    if option_data_requested:
        return True
    return final_label in {
        READY_TO_RESEARCH_WITH_OPTION,
        STOCK_OK_OPTION_BAD,
        OPTION_DATA_NOT_AVAILABLE,
    }


def build_option_contract_criteria(
    profile: StrategyProfile | None,
    *,
    settings: AppSettings | None = None,
    direction: str | None = None,
    final_label: str | None = None,
    option_data_requested: bool = False,
    option_already_supplied: bool = False,
) -> OptionContractCriteria | None:
    if not is_option_relevant(
        final_label or "",
        option_data_requested=option_data_requested,
        option_already_supplied=option_already_supplied,
    ):
        return None

    settings = settings or get_settings()
    direction_clean = (direction or "").strip().upper()
    direction_hint: str | None
    if direction_clean == "LONG":
        direction_hint = "CALL"
    elif direction_clean == "SHORT":
        direction_hint = "PUT"
    else:
        direction_hint = None

    if profile is not None:
        dte_min = profile.option_dte_min
        dte_max = profile.option_dte_max
        premium_min = float(profile.premium_min_usd)
        premium_max = float(profile.premium_max_usd)
        iv_warn = float(profile.iv_warning_threshold)
        iv_reject = float(profile.iv_reject_threshold)
        min_target_margin = float(profile.minimum_target_breakeven_margin_percent)
    else:
        # Conservative defaults that mirror the Balanced Research Default.
        dte_min, dte_max = 45, 90
        premium_min, premium_max = 500.0, 1000.0
        iv_warn, iv_reject = 70.0, 85.0
        min_target_margin = 3.0

    notes: list[str] = []
    if direction_hint is None:
        notes.append(
            "Stock setup direction is undefined; option direction (CALL vs PUT) "
            "must be chosen manually."
        )
    if final_label == STOCK_OK_OPTION_BAD:
        notes.append(
            "The previously supplied option contract failed hard filters; the "
            "criteria below describe what a passing contract would look like."
        )
    if final_label == OPTION_DATA_NOT_AVAILABLE:
        notes.append(
            "No option data has been supplied yet; paste a contract matching the "
            "criteria below to enable option-aware analysis."
        )

    return OptionContractCriteria(
        direction_hint=direction_hint,
        dte_min=int(dte_min),
        dte_max=int(dte_max),
        premium_min_usd=premium_min,
        premium_max_usd=premium_max,
        max_spread_percent=float(settings.option_max_spread_percent),
        min_open_interest=int(settings.option_min_open_interest),
        iv_warning_threshold=iv_warn,
        iv_reject_threshold=iv_reject,
        minimum_target_breakeven_margin_percent=min_target_margin,
        notes=notes,
    )


__all__ = [
    "OptionContractCriteria",
    "build_option_contract_criteria",
    "is_option_relevant",
]
