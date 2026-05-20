"""DB-facing option suitability orchestration (Phase 15, step 15.13).

Evaluates a stored manual option snapshot against the active strategy profile +
stock context (Phase 12 target / current price, optional earnings), and persists
the verdict as an ``OptionCandidate``. Also provides the explicit no-option
fallback so callers can confirm that absent option data yields
``OPTION_DATA_NOT_AVAILABLE`` without touching the stock-only path.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.common.service_utils import ensure_tables
from app.core.config import AppSettings, get_settings
from app.earnings.earnings_models import EarningsEvent
from app.options.manual_option_input_service import ManualOptionInputService
from app.options.manual_option_models import ManualOptionSnapshotRecord
from app.options.option_candidate_models import OptionCandidate
from app.options.option_suitability import (
    OptionFields,
    OptionSuitabilityResult,
    OptionThresholds,
    StockContext,
    evaluate_option_suitability,
)
from app.profiles.profile_manager import profile_manager
from app.quant.stock_setup_models import StockSetup


@dataclass
class OptionEvaluation:
    symbol: str | None
    manual_option_snapshot_id: int | None
    result: OptionSuitabilityResult

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "manual_option_snapshot_id": self.manual_option_snapshot_id,
            "result": self.result.to_dict(),
        }


class OptionSuitabilityService:
    def __init__(
        self,
        settings: AppSettings | None = None,
        manual_option_service: ManualOptionInputService | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.manual_option_service = manual_option_service or ManualOptionInputService()

    def ensure_tables(self, db: Session) -> None:
        ensure_tables(db)

    def _thresholds(self) -> OptionThresholds:
        profile = profile_manager.get_active_profile()
        s = self.settings
        return OptionThresholds(
            dte_min=profile.option_dte_min,
            dte_max=profile.option_dte_max,
            premium_min_usd=float(profile.premium_min_usd),
            premium_max_usd=float(profile.premium_max_usd),
            max_spread_percent=s.option_max_spread_percent,
            min_open_interest=s.option_min_open_interest,
            min_volume_preference=s.option_min_volume_preference,
            iv_warning_threshold=float(profile.iv_warning_threshold),
            iv_reject_threshold=float(profile.iv_reject_threshold),
            iv_fraction_cutoff=s.option_iv_fraction_cutoff,
            minimum_target_breakeven_margin_percent=(
                profile.minimum_target_breakeven_margin_percent
            ),
            max_breakeven_distance_percent=s.option_max_breakeven_distance_percent,
            reject_if_target_below_breakeven=profile.reject_if_target_below_breakeven,
            earnings_risk_window_days=profile.earnings_risk_window_days,
        )

    def _stock_context(self, db: Session, symbol: str | None) -> StockContext:
        if not symbol:
            return StockContext()
        clean = symbol.strip().upper()

        setup = (
            db.query(StockSetup)
            .filter(StockSetup.symbol == clean)
            .order_by(StockSetup.snapshot_date.desc(), StockSetup.id.desc())
            .first()
        )

        earnings_date = None
        now = datetime.now(timezone.utc)
        next_earnings = (
            db.query(EarningsEvent)
            .filter(EarningsEvent.symbol == clean)
            .filter(EarningsEvent.earnings_datetime_utc >= now)
            .order_by(EarningsEvent.earnings_datetime_utc.asc())
            .first()
        )
        if next_earnings is not None and next_earnings.earnings_datetime_utc is not None:
            earnings_date = next_earnings.earnings_datetime_utc.date()

        return StockContext(
            target_price=setup.target_price if setup else None,
            underlying_price=setup.current_close if setup else None,
            earnings_date=earnings_date,
        )

    def _fields_from_record(self, record: ManualOptionSnapshotRecord) -> OptionFields:
        dte = record.dte
        if dte is None and record.expiration_date is not None:
            dte = (record.expiration_date - date.today()).days
        return OptionFields(
            option_type=record.option_type,
            strike=record.strike,
            expiration_date=record.expiration_date,
            dte=dte,
            bid=record.bid,
            ask=record.ask,
            last_price=record.last_price,
            volume=record.volume,
            open_interest=record.open_interest,
            implied_volatility=record.implied_volatility,
            underlying_price=record.underlying_price,
        )

    def evaluate_snapshot(
        self,
        db: Session,
        snapshot_id: int,
        *,
        option_input_requested: bool = False,
    ) -> OptionCandidate:
        self.ensure_tables(db)

        record = self.manual_option_service.get_manual_snapshot_by_id(
            db=db, snapshot_id=snapshot_id
        )
        if record is None:
            raise ValueError(f"Manual option snapshot {snapshot_id} was not found.")

        fields = self._fields_from_record(record)
        stock = self._stock_context(db, record.symbol)
        result = evaluate_option_suitability(
            fields,
            self._thresholds(),
            stock,
            enabled=self.settings.option_suitability_enabled,
            option_input_requested=option_input_requested,
        )

        return self._persist_candidate(
            db=db,
            symbol=record.symbol,
            manual_option_snapshot_id=record.id,
            snapshot_date=record.created_at.date() if record.created_at else date.today(),
            fields=fields,
            stock=stock,
            result=result,
        )

    def evaluate_no_option(
        self,
        db: Session,
        symbol: str | None = None,
        *,
        option_input_requested: bool = False,
    ) -> OptionEvaluation:
        """No-option fallback (step 15.15): returns OPTION_DATA_NOT_AVAILABLE
        (or MANUAL_OPTION_INPUT_NEEDED) without persisting or raising."""
        self.ensure_tables(db)
        stock = self._stock_context(db, symbol)
        result = evaluate_option_suitability(
            OptionFields(),
            self._thresholds(),
            stock,
            enabled=self.settings.option_suitability_enabled,
            option_input_requested=option_input_requested,
        )
        return OptionEvaluation(
            symbol=symbol.upper() if symbol else None,
            manual_option_snapshot_id=None,
            result=result,
        )

    def _persist_candidate(
        self,
        db: Session,
        symbol: str | None,
        manual_option_snapshot_id: int | None,
        snapshot_date: date,
        fields: OptionFields,
        stock: StockContext,
        result: OptionSuitabilityResult,
    ) -> OptionCandidate:
        existing = None
        if manual_option_snapshot_id is not None:
            existing = (
                db.query(OptionCandidate)
                .filter(
                    OptionCandidate.manual_option_snapshot_id == manual_option_snapshot_id
                )
                .one_or_none()
            )

        values = {
            "symbol": symbol.upper() if symbol else None,
            "snapshot_date": snapshot_date,
            "option_type": fields.option_type,
            "strike": fields.strike,
            "expiration_date": fields.expiration_date,
            "dte": fields.dte,
            "premium": result.premium,
            "contract_cost": result.contract_cost,
            "bid": fields.bid,
            "ask": fields.ask,
            "spread_percent": result.spread_percent,
            "open_interest": fields.open_interest,
            "volume": fields.volume,
            "implied_volatility": fields.implied_volatility,
            "iv_percent": result.iv_percent,
            "iv_state": result.iv_state,
            "breakeven": result.breakeven,
            "breakeven_distance_percent": result.breakeven_distance_percent,
            "target_price": stock.target_price,
            "target_margin_percent": result.target_margin_percent,
            "liquidity_score": result.liquidity_score,
            "suitability_label": result.suitability_label,
            "is_suitable": result.is_suitable,
            "data_sufficiency_status": result.data_sufficiency_status,
            "rejection_labels_json": list(result.rejection_labels),
            "warning_labels_json": list(result.warning_labels),
            "outcomes_json": list(result.outcomes),
            "earnings_risk_json": result.earnings_risk,
            "reasons_json": list(result.reasons),
        }

        if existing is None:
            row = OptionCandidate(
                manual_option_snapshot_id=manual_option_snapshot_id,
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


__all__ = ["OptionEvaluation", "OptionSuitabilityService"]
