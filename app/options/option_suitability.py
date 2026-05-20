"""Final option suitability engine (Phase 15, steps 15.12, 15.14, 15.15).

Combines the individual filters, liquidity, IV, breakeven, target, and earnings
modules into a single deterministic verdict for a manually pasted option
contract. The defining contract of this phase: option data is OPTIONAL. When no
usable option fields are present the engine returns ``OPTION_DATA_NOT_AVAILABLE``
(or ``MANUAL_OPTION_INPUT_NEEDED`` when the caller indicated an option was
wanted) -- it never raises and never blocks the stock-only decision.

Overall labels:
    OPTION_SUITABLE, OPTION_DATA_NOT_AVAILABLE, OPTION_ANALYSIS_SKIPPED,
    MANUAL_OPTION_INPUT_NEEDED, STOCK_OK_BUT_OPTION_BAD
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from app.options.breakeven import compute_breakeven
from app.options.earnings_iv_risk import assess_earnings_iv_risk
from app.options.iv_analysis import IV_STATE_UNKNOWN, analyze_iv
from app.options.liquidity_analysis import score_liquidity
from app.options.option_filters import (
    FAIL,
    PASS,
    WARN,
    FilterOutcome,
    compute_premium,
    filter_dte,
    filter_open_interest,
    filter_premium_budget,
    filter_spread,
    volume_preference,
)
from app.options.target_breakeven import evaluate_target_vs_breakeven

# Overall suitability labels.
OPTION_SUITABLE = "OPTION_SUITABLE"
OPTION_DATA_NOT_AVAILABLE = "OPTION_DATA_NOT_AVAILABLE"
OPTION_ANALYSIS_SKIPPED = "OPTION_ANALYSIS_SKIPPED"
MANUAL_OPTION_INPUT_NEEDED = "MANUAL_OPTION_INPUT_NEEDED"
STOCK_OK_BUT_OPTION_BAD = "STOCK_OK_BUT_OPTION_BAD"

SUFFICIENT = "SUFFICIENT"
PARTIAL = "PARTIAL"

# Contract-intrinsic hard filters used to decide data sufficiency.
_INTRINSIC_HARD_FILTERS = frozenset(
    {"dte", "premium_budget", "spread", "open_interest", "iv"}
)
_HARD_FILTERS = _INTRINSIC_HARD_FILTERS | {"breakeven_distance", "target_margin"}


@dataclass(frozen=True)
class OptionFields:
    option_type: str | None = None
    strike: float | None = None
    expiration_date: date | None = None
    dte: int | None = None
    bid: float | None = None
    ask: float | None = None
    last_price: float | None = None
    volume: int | None = None
    open_interest: int | None = None
    implied_volatility: float | None = None
    underlying_price: float | None = None


@dataclass(frozen=True)
class OptionThresholds:
    dte_min: int = 45
    dte_max: int = 90
    premium_min_usd: float = 500.0
    premium_max_usd: float = 1000.0
    max_spread_percent: float = 10.0
    min_open_interest: int = 100
    min_volume_preference: int = 10
    iv_warning_threshold: float = 70.0
    iv_reject_threshold: float = 85.0
    iv_fraction_cutoff: float = 5.0
    minimum_target_breakeven_margin_percent: float = 3.0
    max_breakeven_distance_percent: float = 12.0
    reject_if_target_below_breakeven: bool = True
    earnings_risk_window_days: int = 7


@dataclass(frozen=True)
class StockContext:
    target_price: float | None = None
    underlying_price: float | None = None
    earnings_date: date | None = None


@dataclass(frozen=True)
class OptionSuitabilityResult:
    suitability_label: str
    is_suitable: bool
    data_sufficiency_status: str

    rejection_labels: list[str] = field(default_factory=list)
    warning_labels: list[str] = field(default_factory=list)

    premium: float | None = None
    contract_cost: float | None = None
    spread_percent: float | None = None
    dte: int | None = None
    breakeven: float | None = None
    breakeven_distance_percent: float | None = None
    target_margin_percent: float | None = None
    iv_percent: float | None = None
    iv_state: str = IV_STATE_UNKNOWN
    liquidity_score: int | None = None

    outcomes: list[dict[str, Any]] = field(default_factory=list)
    earnings_risk: dict[str, Any] | None = None
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "suitability_label": self.suitability_label,
            "is_suitable": self.is_suitable,
            "data_sufficiency_status": self.data_sufficiency_status,
            "rejection_labels": list(self.rejection_labels),
            "warning_labels": list(self.warning_labels),
            "premium": self.premium,
            "contract_cost": self.contract_cost,
            "spread_percent": self.spread_percent,
            "dte": self.dte,
            "breakeven": self.breakeven,
            "breakeven_distance_percent": self.breakeven_distance_percent,
            "target_margin_percent": self.target_margin_percent,
            "iv_percent": self.iv_percent,
            "iv_state": self.iv_state,
            "liquidity_score": self.liquidity_score,
            "outcomes": list(self.outcomes),
            "earnings_risk": self.earnings_risk,
            "reasons": list(self.reasons),
        }


def _has_any_option_data(fields: OptionFields, premium: float | None) -> bool:
    return any(
        v is not None
        for v in [
            fields.strike,
            fields.dte,
            fields.expiration_date,
            fields.bid,
            fields.ask,
            fields.last_price,
            fields.volume,
            fields.open_interest,
            fields.implied_volatility,
            premium,
        ]
    )


def evaluate_option_suitability(
    fields: OptionFields,
    thresholds: OptionThresholds | None = None,
    stock: StockContext | None = None,
    *,
    enabled: bool = True,
    option_input_requested: bool = False,
) -> OptionSuitabilityResult:
    thresholds = thresholds or OptionThresholds()

    if not enabled:
        return OptionSuitabilityResult(
            suitability_label=OPTION_ANALYSIS_SKIPPED,
            is_suitable=False,
            data_sufficiency_status=OPTION_ANALYSIS_SKIPPED,
            reasons=["Option analysis is disabled."],
        )

    premium = compute_premium(fields.bid, fields.ask, fields.last_price)

    if not _has_any_option_data(fields, premium):
        label = MANUAL_OPTION_INPUT_NEEDED if option_input_requested else OPTION_DATA_NOT_AVAILABLE
        reason = (
            "An option was requested but none was provided; paste the contract."
            if option_input_requested
            else "No option data available; stock-only analysis is unaffected."
        )
        return OptionSuitabilityResult(
            suitability_label=label,
            is_suitable=False,
            data_sufficiency_status=OPTION_DATA_NOT_AVAILABLE,
            reasons=[reason],
        )

    outcomes: list[FilterOutcome] = [
        filter_dte(fields.dte, thresholds.dte_min, thresholds.dte_max),
        filter_premium_budget(premium, thresholds.premium_min_usd, thresholds.premium_max_usd),
        filter_spread(fields.bid, fields.ask, thresholds.max_spread_percent),
        filter_open_interest(fields.open_interest, thresholds.min_open_interest),
        volume_preference(fields.volume, thresholds.min_volume_preference),
    ]

    iv_result = analyze_iv(
        fields.implied_volatility,
        warning_threshold=thresholds.iv_warning_threshold,
        reject_threshold=thresholds.iv_reject_threshold,
        fraction_cutoff=thresholds.iv_fraction_cutoff,
    )
    outcomes.append(iv_result.outcome)

    breakeven = compute_breakeven(fields.option_type, fields.strike, premium)

    underlying_price = fields.underlying_price
    if underlying_price is None and stock is not None:
        underlying_price = stock.underlying_price
    target_price = stock.target_price if stock is not None else None

    breakeven_distance = None
    target_margin = None
    if breakeven is not None:
        target_result = evaluate_target_vs_breakeven(
            fields.option_type,
            breakeven,
            target_price,
            underlying_price,
            minimum_target_breakeven_margin_percent=(
                thresholds.minimum_target_breakeven_margin_percent
            ),
            max_breakeven_distance_percent=thresholds.max_breakeven_distance_percent,
            reject_if_target_below_breakeven=thresholds.reject_if_target_below_breakeven,
        )
        outcomes.extend(target_result.outcomes)
        breakeven_distance = target_result.breakeven_distance_percent
        target_margin = target_result.target_margin_percent

    earnings_result = assess_earnings_iv_risk(
        stock.earnings_date if stock is not None else None,
        fields.expiration_date,
        iv_result.iv_percent,
        iv_warning_threshold=thresholds.iv_warning_threshold,
    )

    spread_outcome = next((o for o in outcomes if o.name == "spread"), None)
    spread_percent = (
        spread_outcome.value
        if spread_outcome is not None and spread_outcome.status in {PASS, FAIL}
        else None
    )
    liquidity = score_liquidity(
        spread_percent,
        fields.open_interest,
        fields.volume,
        max_spread_percent=thresholds.max_spread_percent,
    )

    rejection_labels = [o.label for o in outcomes if o.is_hard_fail and o.label]
    warning_labels = [o.label for o in outcomes if o.status == WARN and o.label]
    if earnings_result.has_risk and earnings_result.label:
        warning_labels.append(earnings_result.label)

    hard_ran = [o for o in outcomes if o.name in _HARD_FILTERS and o.status in {PASS, FAIL}]

    if rejection_labels:
        label = STOCK_OK_BUT_OPTION_BAD
        is_suitable = False
        reasons = ["Stock may be fine, but the option failed one or more hard filters."]
    elif not hard_ran:
        label = MANUAL_OPTION_INPUT_NEEDED
        is_suitable = False
        reasons = ["Option data present but insufficient to evaluate; paste more fields."]
    else:
        label = OPTION_SUITABLE
        is_suitable = True
        reasons = ["Option passed all applicable hard filters."]

    intrinsic_skipped = any(
        o.name in _INTRINSIC_HARD_FILTERS and o.status not in {PASS, FAIL}
        for o in outcomes
    )
    data_sufficiency = PARTIAL if intrinsic_skipped else SUFFICIENT

    return OptionSuitabilityResult(
        suitability_label=label,
        is_suitable=is_suitable,
        data_sufficiency_status=data_sufficiency,
        rejection_labels=rejection_labels,
        warning_labels=warning_labels,
        premium=premium,
        contract_cost=premium * 100.0 if premium is not None else None,
        spread_percent=spread_percent,
        dte=fields.dte,
        breakeven=breakeven,
        breakeven_distance_percent=breakeven_distance,
        target_margin_percent=target_margin,
        iv_percent=iv_result.iv_percent,
        iv_state=iv_result.state,
        liquidity_score=liquidity.score,
        outcomes=[o.to_dict() for o in outcomes],
        earnings_risk=earnings_result.to_dict(),
        reasons=reasons,
    )


__all__ = [
    "MANUAL_OPTION_INPUT_NEEDED",
    "OPTION_ANALYSIS_SKIPPED",
    "OPTION_DATA_NOT_AVAILABLE",
    "OPTION_SUITABLE",
    "PARTIAL",
    "STOCK_OK_BUT_OPTION_BAD",
    "SUFFICIENT",
    "OptionFields",
    "OptionSuitabilityResult",
    "OptionThresholds",
    "StockContext",
    "evaluate_option_suitability",
]
