"""Phase 20 — DB-facing orchestration for the Hard Filter Gate.

Builds the gate inputs from existing tables (Phase 12 ``StockSetup``,
Phase 13 ``MarketRegimeSnapshot``, Phase 10 ``EarningsRiskSnapshot``),
applies ``HardFilterGate``, and -- when requested -- persists the
decision into ``hard_filter_results``.

Manual option snapshots are passed in by the caller (typically the
existing manual-option endpoints already exercised by Phase 15). The
service intentionally does not load option data implicitly, so the
Phase 20 invariant "missing option data is not a hard rejection"
remains true by construction.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.common.service_utils import ensure_tables
from app.core.config import AppSettings, get_settings
from app.earnings.earnings_models import EarningsRiskSnapshot
from app.hard_filter.hard_filter_gate import (
    EarningsContext,
    HardFilterDecision,
    HardFilterGate,
    OptionContext,
    RegimeContext,
    StockContext,
)
from app.hard_filter.hard_filter_models import HardFilterResult
from app.market_regime.market_regime_models import MarketRegimeSnapshot
from app.options.manual_option_models import ManualOptionSnapshotRecord
from app.profiles.profile_models import StrategyProfile
from app.quant.stock_setup_models import StockSetup


@dataclass
class HardFilterEvaluation:
    decision: HardFilterDecision
    record: HardFilterResult | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision.to_dict(),
            "record_id": self.record.id if self.record is not None else None,
        }


class HardFilterService:
    def __init__(
        self,
        settings: AppSettings | None = None,
        gate: HardFilterGate | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.gate = gate or HardFilterGate(settings=self.settings)

    def ensure_tables(self, db: Session) -> None:
        ensure_tables(db)

    # ---------------------------------------------------------------- entry pt

    def evaluate_symbol(
        self,
        db: Session,
        symbol: str,
        *,
        option_snapshot: ManualOptionSnapshotRecord | None = None,
        profile: StrategyProfile | None = None,
        persist: bool = True,
    ) -> HardFilterEvaluation:
        self.ensure_tables(db)

        clean = (symbol or "").strip().upper()
        if not clean:
            raise ValueError("symbol is required")

        stock = self._stock_context(db, clean)
        regime = self._regime_context(db)
        earnings = self._earnings_context(db, clean, option_snapshot=option_snapshot)
        option = self._option_context(option_snapshot)

        decision = self.gate.evaluate(
            stock=stock,
            option=option,
            regime=regime,
            earnings=earnings,
            profile=profile,
        )

        record: HardFilterResult | None = None
        if persist and stock.snapshot_date is not None:
            record = self._persist(db=db, decision=decision, snapshot_date=stock.snapshot_date)

        return HardFilterEvaluation(decision=decision, record=record)

    # --------------------------------------------------------------- loaders

    def _stock_context(self, db: Session, symbol: str) -> StockContext:
        setup: StockSetup | None = (
            db.query(StockSetup)
            .filter(StockSetup.symbol == symbol)
            .order_by(StockSetup.snapshot_date.desc(), StockSetup.id.desc())
            .first()
        )
        if setup is None:
            return StockContext(symbol=symbol)

        return StockContext(
            symbol=symbol,
            snapshot_date=setup.snapshot_date,
            direction=setup.direction,
            current_close=setup.current_close,
            nearest_support=setup.nearest_support,
            nearest_resistance=setup.nearest_resistance,
            sma_50=setup.sma_50,
            atr_14=setup.atr_14,
            stock_risk_reward=setup.stock_risk_reward,
            target_price=setup.target_price,
        )

    def _regime_context(self, db: Session) -> RegimeContext:
        snapshot: MarketRegimeSnapshot | None = (
            db.query(MarketRegimeSnapshot)
            .order_by(MarketRegimeSnapshot.snapshot_date.desc(), MarketRegimeSnapshot.id.desc())
            .first()
        )
        if snapshot is None:
            return RegimeContext()
        return RegimeContext(
            regime_label=snapshot.regime_label,
            regime_score=snapshot.regime_score,
        )

    def _earnings_context(
        self,
        db: Session,
        symbol: str,
        *,
        option_snapshot: ManualOptionSnapshotRecord | None,
    ) -> EarningsContext:
        snapshot: EarningsRiskSnapshot | None = (
            db.query(EarningsRiskSnapshot)
            .filter(EarningsRiskSnapshot.symbol == symbol)
            .order_by(
                EarningsRiskSnapshot.snapshot_date.desc(),
                EarningsRiskSnapshot.id.desc(),
            )
            .first()
        )
        if snapshot is None:
            return EarningsContext()

        ebe = (snapshot.earnings_before_expiration or "NOT_APPLICABLE").upper()
        # If we have an option expiration date in the manual snapshot and the
        # earnings snapshot was computed without it, the persisted value may
        # be ``NOT_APPLICABLE``. The gate trusts whatever the persisted value
        # says -- it does not re-evaluate earnings vs expiration here.
        return EarningsContext(
            risk_label=snapshot.risk_label,
            days_to_earnings=snapshot.days_to_earnings,
            earnings_within_window=bool(snapshot.earnings_within_window),
            earnings_before_expiration=ebe,
            earnings_risk_window_days=snapshot.earnings_risk_window_days,
        )

    def _option_context(
        self, snapshot: ManualOptionSnapshotRecord | None
    ) -> OptionContext:
        if snapshot is None:
            return OptionContext()
        return OptionContext(
            option_type=snapshot.option_type,
            strike=snapshot.strike,
            dte=snapshot.dte,
            expiration_date=snapshot.expiration_date,
            bid=snapshot.bid,
            ask=snapshot.ask,
            last_price=snapshot.last_price,
            open_interest=snapshot.open_interest,
            implied_volatility=snapshot.implied_volatility,
            underlying_price=snapshot.underlying_price,
        )

    # -------------------------------------------------------------- persistence

    def _persist(
        self,
        db: Session,
        decision: HardFilterDecision,
        snapshot_date: date,
    ) -> HardFilterResult:
        existing = (
            db.query(HardFilterResult)
            .filter(HardFilterResult.symbol == decision.symbol)
            .filter(HardFilterResult.snapshot_date == snapshot_date)
            .one_or_none()
        )

        values = {
            "overall_decision": decision.overall_decision,
            "option_decision": decision.option_decision,
            "outcomes_json": [o.to_dict() for o in decision.outcomes],
            "stock_blocking_labels_json": list(decision.stock_blocking_labels),
            "option_blocking_labels_json": list(decision.option_blocking_labels),
            "warning_labels_json": list(decision.warning_labels),
            "skipped_filters_json": list(decision.skipped_filters),
            "reasons_json": list(decision.reasons),
            "profile_name": decision.profile_name,
            "profile_version": decision.profile_version,
            "stock_risk_reward": decision.stock_risk_reward,
            "price_extension_atr": decision.price_extension_atr,
            "price_extension_sma50_percent": decision.price_extension_sma50_percent,
            "regime_label": decision.regime_label,
            "earnings_risk_label": decision.earnings_risk_label,
        }

        if existing is None:
            row = HardFilterResult(
                symbol=decision.symbol,
                snapshot_date=snapshot_date,
                **values,
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            return row

        for key, value in values.items():
            setattr(existing, key, value)
        db.commit()
        db.refresh(existing)
        return existing


__all__ = ["HardFilterEvaluation", "HardFilterService"]
