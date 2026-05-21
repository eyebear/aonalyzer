"""Phase 20 — Hard Filter Gate.

Non-negotiable rules layered on top of the Phase 19 data sufficiency gate.

Principle (verbatim from the Phase 20 outline):

* Stock hard filters always run.
* Option hard filters run only when option data exists.
* Missing option data is **not** itself a hard rejection.

Stock filters covered:

* ``20.2`` stock risk/reward
* ``20.3`` price extension (ATR multiple + SMA50 percent)
* ``20.4`` market regime hard warning (warning, not block)
* ``20.5`` earnings risk (warning by default, fail when option expires
  before earnings)

Optional option filters (run only when the relevant field is present;
otherwise produce ``SKIPPED`` outcomes -- never failures):

* ``20.6`` DTE
* ``20.7`` target below breakeven
* ``20.8`` spread
* ``20.9`` open interest
* ``20.10`` IV extreme

The gate reuses the existing ``app.options.option_filters``,
``app.options.target_breakeven`` and ``app.options.iv_analysis`` primitives
rather than re-implementing them. The output is a ``HardFilterDecision``
dataclass with deterministic JSON via ``to_dict()``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from app.core.config import AppSettings, get_settings
from app.options.breakeven import compute_breakeven
from app.options.iv_analysis import IV_STATE_UNKNOWN, IV_TOO_HIGH, analyze_iv
from app.options.option_filters import (
    FAIL,
    PASS,
    SKIPPED,
    WARN,
    FilterOutcome,
    compute_premium,
    filter_dte,
    filter_open_interest,
    filter_spread,
)
from app.options.target_breakeven import evaluate_target_vs_breakeven
from app.profiles.profile_manager import profile_manager
from app.profiles.profile_models import StrategyProfile

# --- Hard-filter rejection / warning labels ---------------------------------

# Stock filters.
WEAK_STOCK_RISK_REWARD = "WEAK_STOCK_RISK_REWARD"
PRICE_TOO_EXTENDED = "PRICE_TOO_EXTENDED"
REGIME_OPPOSES_SETUP = "REGIME_OPPOSES_SETUP"
EARNINGS_INSIDE_WINDOW = "EARNINGS_INSIDE_WINDOW"
EARNINGS_BEFORE_OPTION_EXPIRATION = "EARNINGS_BEFORE_OPTION_EXPIRATION"

# Overall decision states.
DECISION_ALLOWED = "ALLOWED"
DECISION_BLOCKED = "BLOCKED"

OPTION_DECISION_NOT_EVALUATED = "OPTION_NOT_EVALUATED"
OPTION_DECISION_ALLOWED = "OPTION_ALLOWED"
OPTION_DECISION_BLOCKED = "OPTION_BLOCKED"

# Stock-side filter names (used to scope which outcomes participate in the
# stock decision vs the option decision).
_STOCK_FILTER_NAMES = frozenset(
    {
        "stock_risk_reward",
        "price_extension",
        "market_regime",
        "earnings_risk",
    }
)


# --- Inputs / outputs -------------------------------------------------------


@dataclass(frozen=True)
class StockContext:
    """Pre-computed stock-side inputs (typically from ``StockSetup``)."""

    symbol: str | None = None
    snapshot_date: date | None = None
    direction: str | None = None  # "LONG" / "SHORT" / "UNDEFINED"
    current_close: float | None = None
    nearest_support: float | None = None
    nearest_resistance: float | None = None
    sma_50: float | None = None
    atr_14: float | None = None
    stock_risk_reward: float | None = None
    target_price: float | None = None


@dataclass(frozen=True)
class OptionContext:
    """Optional option inputs.

    All fields default to ``None``; the gate treats the entire context as
    "no option data was supplied" only when ``has_data()`` returns ``False``.
    """

    option_type: str | None = None
    strike: float | None = None
    dte: int | None = None
    expiration_date: date | None = None
    bid: float | None = None
    ask: float | None = None
    last_price: float | None = None
    open_interest: int | None = None
    implied_volatility: float | None = None
    underlying_price: float | None = None

    def has_data(self) -> bool:
        return any(
            v is not None
            for v in (
                self.option_type,
                self.strike,
                self.dte,
                self.expiration_date,
                self.bid,
                self.ask,
                self.last_price,
                self.open_interest,
                self.implied_volatility,
            )
        )


@dataclass(frozen=True)
class RegimeContext:
    regime_label: str | None = None  # RISK_ON / NEUTRAL / RISK_OFF / UNKNOWN
    regime_score: int | None = None


@dataclass(frozen=True)
class EarningsContext:
    """Pre-computed earnings risk inputs.

    Mirrors the ``EarningsRiskSnapshot`` fields the gate cares about.
    """

    risk_label: str | None = None
    days_to_earnings: int | None = None
    earnings_within_window: bool = False
    earnings_before_expiration: str = "NOT_APPLICABLE"  # TRUE/FALSE/NOT_APPLICABLE
    earnings_risk_window_days: int | None = None


@dataclass(frozen=True)
class HardFilterOutcome:
    """A single filter outcome -- matches the option_filters ``FilterOutcome``
    shape but carries a Phase 20 category flag so the gate can split stock
    vs option outcomes deterministically."""

    name: str
    category: str  # "stock" | "option"
    status: str    # PASS / FAIL / WARN / SKIPPED
    label: str | None = None
    detail: str | None = None
    value: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "category": self.category,
            "status": self.status,
            "label": self.label,
            "detail": self.detail,
            "value": self.value,
        }


@dataclass(frozen=True)
class HardFilterDecision:
    symbol: str | None
    overall_decision: str
    option_decision: str

    outcomes: list[HardFilterOutcome] = field(default_factory=list)
    stock_blocking_labels: list[str] = field(default_factory=list)
    option_blocking_labels: list[str] = field(default_factory=list)
    warning_labels: list[str] = field(default_factory=list)
    skipped_filters: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)

    profile_name: str | None = None
    profile_version: str | None = None

    # Scalars used by ``HardFilterResult`` storage and downstream phases.
    stock_risk_reward: float | None = None
    price_extension_atr: float | None = None
    price_extension_sma50_percent: float | None = None
    regime_label: str | None = None
    earnings_risk_label: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "overall_decision": self.overall_decision,
            "option_decision": self.option_decision,
            "outcomes": [o.to_dict() for o in self.outcomes],
            "stock_blocking_labels": list(self.stock_blocking_labels),
            "option_blocking_labels": list(self.option_blocking_labels),
            "warning_labels": list(self.warning_labels),
            "skipped_filters": list(self.skipped_filters),
            "reasons": list(self.reasons),
            "profile_name": self.profile_name,
            "profile_version": self.profile_version,
            "stock_risk_reward": self.stock_risk_reward,
            "price_extension_atr": self.price_extension_atr,
            "price_extension_sma50_percent": self.price_extension_sma50_percent,
            "regime_label": self.regime_label,
            "earnings_risk_label": self.earnings_risk_label,
        }


# --- The gate ---------------------------------------------------------------


class HardFilterGate:
    """Apply non-negotiable rules to a stock (and, when present, option) context."""

    def __init__(self, settings: AppSettings | None = None) -> None:
        self.settings = settings or get_settings()

    # ---------------------------------------------------------------- entry pt

    def evaluate(
        self,
        stock: StockContext,
        *,
        option: OptionContext | None = None,
        regime: RegimeContext | None = None,
        earnings: EarningsContext | None = None,
        profile: StrategyProfile | None = None,
    ) -> HardFilterDecision:
        active_profile = profile or self._safe_active_profile()
        option_ctx = option or OptionContext()
        regime_ctx = regime or RegimeContext()
        earnings_ctx = earnings or EarningsContext()

        outcomes: list[HardFilterOutcome] = []

        # ---- Stock filters (always run) ------------------------------------
        outcomes.append(self._filter_stock_risk_reward(stock, active_profile))
        ext_outcome, ext_atr, ext_sma50_pct = self._filter_price_extension(stock)
        outcomes.append(ext_outcome)
        outcomes.append(self._filter_market_regime(stock, regime_ctx))
        outcomes.append(self._filter_earnings_risk(earnings_ctx, option_ctx))

        # ---- Optional option filters --------------------------------------
        option_has_data = option_ctx.has_data()
        if option_has_data:
            outcomes.extend(self._option_filters(option_ctx, stock, active_profile))
        else:
            # Step 20.6-20.10 -- each filter is SKIPPED, never FAIL. This is
            # the defining Phase 20 invariant: missing option data is not a
            # hard rejection.
            for name in (
                "option_dte",
                "option_target_breakeven",
                "option_spread",
                "option_open_interest",
                "option_iv_extreme",
            ):
                outcomes.append(
                    HardFilterOutcome(
                        name=name,
                        category="option",
                        status=SKIPPED,
                        detail="No option data supplied; option hard filters skipped.",
                    )
                )

        # ---- Aggregate decisions ------------------------------------------
        stock_outcomes = [o for o in outcomes if o.category == "stock"]
        option_outcomes = [o for o in outcomes if o.category == "option"]

        stock_blocking = [o.label for o in stock_outcomes if o.status == FAIL and o.label]
        option_blocking = [o.label for o in option_outcomes if o.status == FAIL and o.label]
        warnings = [o.label for o in outcomes if o.status == WARN and o.label]
        skipped = [o.name for o in outcomes if o.status == SKIPPED]

        reasons: list[str] = []
        for o in outcomes:
            if o.status in {FAIL, WARN} and o.detail:
                reasons.append(o.detail)

        overall = DECISION_BLOCKED if stock_blocking else DECISION_ALLOWED

        if not option_has_data:
            option_decision = OPTION_DECISION_NOT_EVALUATED
        elif option_blocking:
            option_decision = OPTION_DECISION_BLOCKED
        else:
            option_decision = OPTION_DECISION_ALLOWED

        return HardFilterDecision(
            symbol=stock.symbol,
            overall_decision=overall,
            option_decision=option_decision,
            outcomes=outcomes,
            stock_blocking_labels=_dedupe(stock_blocking),
            option_blocking_labels=_dedupe(option_blocking),
            warning_labels=_dedupe(warnings),
            skipped_filters=_dedupe(skipped),
            reasons=reasons,
            profile_name=active_profile.profile_name if active_profile else None,
            profile_version=active_profile.profile_version if active_profile else None,
            stock_risk_reward=stock.stock_risk_reward,
            price_extension_atr=ext_atr,
            price_extension_sma50_percent=ext_sma50_pct,
            regime_label=regime_ctx.regime_label,
            earnings_risk_label=earnings_ctx.risk_label,
        )

    # ---------------------------------------------------------------- stock fs

    def _filter_stock_risk_reward(
        self, stock: StockContext, profile: StrategyProfile | None
    ) -> HardFilterOutcome:
        minimum = (
            float(profile.minimum_risk_reward)
            if profile is not None
            else self.settings.hard_filter_min_stock_risk_reward
        )
        rr = stock.stock_risk_reward
        if rr is None:
            return HardFilterOutcome(
                name="stock_risk_reward",
                category="stock",
                status=SKIPPED,
                detail="No stock_risk_reward computed; setup math may still be pending.",
            )
        if rr < minimum:
            return HardFilterOutcome(
                name="stock_risk_reward",
                category="stock",
                status=FAIL,
                label=WEAK_STOCK_RISK_REWARD,
                detail=(
                    f"Stock R:R {rr:.2f} is below the minimum {minimum:.2f}."
                ),
                value=float(rr),
            )
        return HardFilterOutcome(
            name="stock_risk_reward",
            category="stock",
            status=PASS,
            detail=f"Stock R:R {rr:.2f} meets the minimum {minimum:.2f}.",
            value=float(rr),
        )

    def _filter_price_extension(
        self, stock: StockContext
    ) -> tuple[HardFilterOutcome, float | None, float | None]:
        """Step 20.3 -- avoid chasing.

        Two complementary checks; either firing produces a FAIL with the
        ``PRICE_TOO_EXTENDED`` label. The check is direction-aware: only
        LONG setups are gated (a SHORT setup that is "extended below" is
        not a chase in the same way).

        Returns the outcome plus the raw ATR multiple and SMA50 percent
        for storage / dashboards.
        """
        # Direction guard: undefined or short -- skip rather than fail.
        direction = (stock.direction or "").strip().upper()
        if direction != "LONG":
            return (
                HardFilterOutcome(
                    name="price_extension",
                    category="stock",
                    status=SKIPPED,
                    detail=(
                        "Price extension is gated for LONG setups only; "
                        f"direction='{direction or 'UNDEFINED'}'."
                    ),
                ),
                None,
                None,
            )

        if stock.current_close is None:
            return (
                HardFilterOutcome(
                    name="price_extension",
                    category="stock",
                    status=SKIPPED,
                    detail="No current_close to measure price extension.",
                ),
                None,
                None,
            )

        atr_mult: float | None = None
        if stock.atr_14 not in (None, 0) and stock.nearest_support is not None:
            atr_mult = (
                (float(stock.current_close) - float(stock.nearest_support))
                / float(stock.atr_14)
            )

        sma50_pct: float | None = None
        if stock.sma_50 not in (None, 0):
            sma50_pct = (
                (float(stock.current_close) - float(stock.sma_50))
                / float(stock.sma_50)
                * 100.0
            )

        atr_threshold = self.settings.hard_filter_max_atr_extension_multiple
        sma_threshold = self.settings.hard_filter_max_sma50_extension_percent

        fail_reasons: list[str] = []
        if atr_mult is not None and atr_mult > atr_threshold:
            fail_reasons.append(
                f"price is {atr_mult:.2f} ATR above nearest support (limit {atr_threshold:.2f})"
            )
        if sma50_pct is not None and sma50_pct > sma_threshold:
            fail_reasons.append(
                f"price is {sma50_pct:.2f}% above SMA50 (limit {sma_threshold:.2f}%)"
            )

        if not fail_reasons and atr_mult is None and sma50_pct is None:
            return (
                HardFilterOutcome(
                    name="price_extension",
                    category="stock",
                    status=SKIPPED,
                    detail=(
                        "No ATR or SMA50 reference available to measure "
                        "price extension."
                    ),
                ),
                atr_mult,
                sma50_pct,
            )

        if fail_reasons:
            return (
                HardFilterOutcome(
                    name="price_extension",
                    category="stock",
                    status=FAIL,
                    label=PRICE_TOO_EXTENDED,
                    detail=(
                        "Setup is chasing: " + "; ".join(fail_reasons) + "."
                    ),
                    value=atr_mult if atr_mult is not None else sma50_pct,
                ),
                atr_mult,
                sma50_pct,
            )

        return (
            HardFilterOutcome(
                name="price_extension",
                category="stock",
                status=PASS,
                detail=(
                    "Price extension within tolerance "
                    f"(ATR mult={atr_mult}, SMA50 %={sma50_pct})."
                ),
                value=atr_mult if atr_mult is not None else sma50_pct,
            ),
            atr_mult,
            sma50_pct,
        )

    def _filter_market_regime(
        self, stock: StockContext, regime: RegimeContext
    ) -> HardFilterOutcome:
        """Step 20.4 -- the market regime check is a WARNING, not a FAIL.

        The Phase 20 outline calls it a "hard warning" -- the gate surfaces
        the warning label and lets the decision engine (Phase 21) decide
        what to do with it. Regime alone never blocks a stock decision.
        """
        regime_label = (regime.regime_label or "").strip().upper()
        direction = (stock.direction or "").strip().upper()

        if not regime_label or regime_label == "UNKNOWN":
            return HardFilterOutcome(
                name="market_regime",
                category="stock",
                status=SKIPPED,
                detail="No market regime read available.",
            )

        opposes = (
            (direction == "LONG" and regime_label == "RISK_OFF")
            or (direction == "SHORT" and regime_label == "RISK_ON")
        )
        if opposes:
            return HardFilterOutcome(
                name="market_regime",
                category="stock",
                status=WARN,
                label=REGIME_OPPOSES_SETUP,
                detail=(
                    f"Broad-market regime is {regime_label} while the setup "
                    f"is {direction}; treat with caution."
                ),
            )
        return HardFilterOutcome(
            name="market_regime",
            category="stock",
            status=PASS,
            detail=f"Market regime {regime_label} is not opposing a {direction} setup.",
        )

    def _filter_earnings_risk(
        self,
        earnings: EarningsContext,
        option: OptionContext,
    ) -> HardFilterOutcome:
        """Step 20.5 -- earnings risk.

        Behaviour matrix:

        * ``earnings_before_expiration == "TRUE"`` -> always FAIL with
          ``EARNINGS_BEFORE_OPTION_EXPIRATION`` (option-side risk).
        * ``earnings_within_window`` -> WARN with ``EARNINGS_INSIDE_WINDOW``
          unless ``hard_filter_earnings_inside_window_blocks`` is enabled
          (in which case FAIL). Defaults to WARN.
        * Otherwise PASS, or SKIPPED when no earnings context exists.
        """
        if (earnings.earnings_before_expiration or "").upper() == "TRUE":
            return HardFilterOutcome(
                name="earnings_risk",
                category="stock",
                status=FAIL,
                label=EARNINGS_BEFORE_OPTION_EXPIRATION,
                detail=(
                    "Earnings event falls before the option expiration date; "
                    "this hard fail is non-bypassable."
                ),
            )

        if earnings.earnings_within_window:
            status = (
                FAIL
                if self.settings.hard_filter_earnings_inside_window_blocks
                else WARN
            )
            return HardFilterOutcome(
                name="earnings_risk",
                category="stock",
                status=status,
                label=EARNINGS_INSIDE_WINDOW,
                detail=(
                    f"Next earnings is {earnings.days_to_earnings} days away; "
                    f"inside the {earnings.earnings_risk_window_days}-day "
                    "risk window."
                ),
                value=(
                    float(earnings.days_to_earnings)
                    if earnings.days_to_earnings is not None
                    else None
                ),
            )

        if earnings.risk_label in (None, "", "EARNINGS_DATA_NOT_AVAILABLE"):
            return HardFilterOutcome(
                name="earnings_risk",
                category="stock",
                status=SKIPPED,
                detail="No earnings risk snapshot available.",
            )

        return HardFilterOutcome(
            name="earnings_risk",
            category="stock",
            status=PASS,
            detail=f"Earnings risk OK ({earnings.risk_label}).",
        )

    # --------------------------------------------------------------- option fs

    def _option_filters(
        self,
        option: OptionContext,
        stock: StockContext,
        profile: StrategyProfile | None,
    ) -> list[HardFilterOutcome]:
        outs: list[HardFilterOutcome] = []

        dte_min = profile.option_dte_min if profile is not None else 45
        dte_max = profile.option_dte_max if profile is not None else 90
        iv_warning = (
            float(profile.iv_warning_threshold) if profile is not None else 70.0
        )
        iv_reject = (
            float(profile.iv_reject_threshold) if profile is not None else 85.0
        )
        max_spread_pct = self.settings.option_max_spread_percent
        min_oi = self.settings.option_min_open_interest
        max_bd_pct = self.settings.option_max_breakeven_distance_percent
        min_target_margin = (
            float(profile.minimum_target_breakeven_margin_percent)
            if profile is not None
            else 3.0
        )
        reject_target_below = (
            bool(profile.reject_if_target_below_breakeven) if profile is not None else True
        )
        iv_fraction_cutoff = self.settings.option_iv_fraction_cutoff

        # 20.6 -- DTE
        outs.append(
            _adapt(filter_dte(option.dte, dte_min, dte_max), name="option_dte")
        )

        # 20.7 -- target below breakeven (reuses the Phase 15 evaluator)
        premium = compute_premium(option.bid, option.ask, option.last_price)
        breakeven = compute_breakeven(option.option_type, option.strike, premium)
        underlying = option.underlying_price or stock.current_close
        target_price = stock.target_price
        if breakeven is None:
            outs.append(
                HardFilterOutcome(
                    name="option_target_breakeven",
                    category="option",
                    status=SKIPPED,
                    detail=(
                        "Cannot compute breakeven; missing strike, premium, "
                        "or option type."
                    ),
                )
            )
        else:
            tb = evaluate_target_vs_breakeven(
                option.option_type,
                breakeven,
                target_price,
                underlying,
                minimum_target_breakeven_margin_percent=min_target_margin,
                max_breakeven_distance_percent=max_bd_pct,
                reject_if_target_below_breakeven=reject_target_below,
            )
            # Only the ``target_margin`` outcome matters for step 20.7; the
            # ``breakeven_distance`` outcome is informational here and is
            # rolled into the same option filter slot.
            for o in tb.outcomes:
                if o.name == "target_margin":
                    outs.append(_adapt(o, name="option_target_breakeven"))
                    break
            else:  # pragma: no cover -- defensive
                outs.append(
                    HardFilterOutcome(
                        name="option_target_breakeven",
                        category="option",
                        status=SKIPPED,
                        detail="Target/breakeven evaluator returned no outcome.",
                    )
                )

        # 20.8 -- spread
        outs.append(
            _adapt(
                filter_spread(option.bid, option.ask, max_spread_pct),
                name="option_spread",
            )
        )

        # 20.9 -- open interest
        outs.append(
            _adapt(
                filter_open_interest(option.open_interest, min_oi),
                name="option_open_interest",
            )
        )

        # 20.10 -- IV extreme
        iv_result = analyze_iv(
            option.implied_volatility,
            warning_threshold=iv_warning,
            reject_threshold=iv_reject,
            fraction_cutoff=iv_fraction_cutoff,
        )
        # ``analyze_iv`` returns PASS / WARN / FAIL / SKIPPED. Only the FAIL
        # case is a hard rejection for Phase 20.10; WARN keeps the IV state
        # label so dashboards can render "elevated IV". The IV state itself
        # is informational and is dropped on the floor here -- the
        # suitability engine still surfaces it elsewhere.
        if iv_result.state == IV_STATE_UNKNOWN:
            outs.append(
                HardFilterOutcome(
                    name="option_iv_extreme",
                    category="option",
                    status=SKIPPED,
                    detail="No implied volatility supplied.",
                )
            )
        else:
            inner = iv_result.outcome
            outs.append(
                HardFilterOutcome(
                    name="option_iv_extreme",
                    category="option",
                    status=inner.status,
                    label=IV_TOO_HIGH if inner.status == FAIL else None,
                    detail=inner.detail,
                    value=inner.value,
                )
            )

        return outs

    # --------------------------------------------------------------- helpers

    @staticmethod
    def _safe_active_profile() -> StrategyProfile | None:
        try:
            return profile_manager.get_active_profile()
        except Exception:
            return None


def _adapt(outcome: FilterOutcome, name: str) -> HardFilterOutcome:
    """Convert a ``FilterOutcome`` into a Phase 20 outcome with category."""
    return HardFilterOutcome(
        name=name,
        category="option",
        status=outcome.status,
        label=outcome.label,
        detail=outcome.detail,
        value=outcome.value,
    )


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for v in values:
        if v in seen:
            continue
        seen.add(v)
        out.append(v)
    return out


__all__ = [
    "DECISION_ALLOWED",
    "DECISION_BLOCKED",
    "EARNINGS_BEFORE_OPTION_EXPIRATION",
    "EARNINGS_INSIDE_WINDOW",
    "EarningsContext",
    "HardFilterDecision",
    "HardFilterGate",
    "HardFilterOutcome",
    "OPTION_DECISION_ALLOWED",
    "OPTION_DECISION_BLOCKED",
    "OPTION_DECISION_NOT_EVALUATED",
    "OptionContext",
    "PRICE_TOO_EXTENDED",
    "REGIME_OPPOSES_SETUP",
    "RegimeContext",
    "StockContext",
    "WEAK_STOCK_RISK_REWARD",
]
