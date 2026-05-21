"""Phase 22 — DB-facing orchestration for the action suggestion layer.

Calls the Phase 21 ``DecisionService`` for the upstream decision, builds
the Phase 22 package via ``format_action_package``, and -- when
persistence is requested -- upserts into ``action_suggestions``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.action.action_labels import lifecycle_state_for
from app.action.action_models import ActionSuggestion
from app.action.action_package_formatter import (
    ActionFormatterInputs,
    ActionPackage,
    format_action_package,
)
from app.action.entry_condition_builder import StockSetupSnapshot
from app.common.service_utils import ensure_tables
from app.core.config import AppSettings, get_settings
from app.decision.decision_service import DecisionService
from app.earnings.earnings_models import EarningsRiskSnapshot
from app.options.manual_option_input_service import ManualOptionInputService
from app.profiles.profile_manager import profile_manager
from app.profiles.profile_models import StrategyProfile
from app.quant.stock_setup_models import StockSetup


@dataclass
class ActionEvaluation:
    package: ActionPackage
    record: ActionSuggestion | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "package": self.package.to_dict(),
            "record_id": self.record.id if self.record is not None else None,
        }


class ActionSuggestionService:
    def __init__(
        self,
        settings: AppSettings | None = None,
        decision_service: DecisionService | None = None,
        manual_option_service: ManualOptionInputService | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.decision_service = decision_service or DecisionService(settings=self.settings)
        self.manual_option_service = manual_option_service or ManualOptionInputService()

    def ensure_tables(self, db: Session) -> None:
        ensure_tables(db)

    # ---------------------------------------------------------------- entry pt

    def evaluate_symbol(
        self,
        db: Session,
        symbol: str,
        *,
        manual_option_snapshot_id: int | None = None,
        option_data_requested: bool = False,
        persist: bool = True,
        profile: StrategyProfile | None = None,
    ) -> ActionEvaluation:
        self.ensure_tables(db)
        clean = (symbol or "").strip().upper()
        if not clean:
            raise ValueError("symbol is required")

        active_profile = profile or self._safe_profile()

        # Phase 21 decision -- do not persist from here; the action service
        # is independent and a caller may run either layer separately.
        decision_eval = self.decision_service.evaluate_symbol(
            db=db,
            symbol=clean,
            manual_option_snapshot_id=manual_option_snapshot_id,
            option_data_requested=option_data_requested,
            persist=False,
            profile=active_profile,
        )
        decision = decision_eval.decision

        option_already_supplied = manual_option_snapshot_id is not None

        inputs = self._build_formatter_inputs(
            db=db,
            symbol=clean,
            option_already_supplied=option_already_supplied,
            option_data_requested=option_data_requested,
        )

        package = format_action_package(
            decision=decision,
            inputs=inputs,
            profile=active_profile,
            settings=self.settings,
        )

        record: ActionSuggestion | None = None
        if persist:
            snapshot_date = decision.snapshot_date or date.today()
            record = self._persist(
                db=db,
                package=package,
                snapshot_date=snapshot_date,
            )

        return ActionEvaluation(package=package, record=record)

    # ----------------------------------------------------------- helpers

    def _safe_profile(self) -> StrategyProfile | None:
        try:
            return profile_manager.get_active_profile()
        except Exception:
            return None

    def _build_formatter_inputs(
        self,
        db: Session,
        symbol: str,
        option_already_supplied: bool,
        option_data_requested: bool,
    ) -> ActionFormatterInputs:
        setup: StockSetup | None = (
            db.query(StockSetup)
            .filter(StockSetup.symbol == symbol)
            .order_by(StockSetup.snapshot_date.desc(), StockSetup.id.desc())
            .first()
        )
        setup_snapshot = (
            StockSetupSnapshot(
                direction=setup.direction,
                current_close=setup.current_close,
                entry_zone_low=setup.entry_zone_low,
                entry_zone_high=setup.entry_zone_high,
                nearest_support=setup.nearest_support,
                nearest_resistance=setup.nearest_resistance,
            )
            if setup is not None
            else StockSetupSnapshot()
        )
        stop_price = setup.stop_price if setup is not None else None

        earnings: EarningsRiskSnapshot | None = (
            db.query(EarningsRiskSnapshot)
            .filter(EarningsRiskSnapshot.symbol == symbol)
            .order_by(
                EarningsRiskSnapshot.snapshot_date.desc(),
                EarningsRiskSnapshot.id.desc(),
            )
            .first()
        )
        days_to_earnings = earnings.days_to_earnings if earnings else None
        next_earnings_iso = (
            earnings.next_earnings_datetime_utc.isoformat()
            if earnings is not None and earnings.next_earnings_datetime_utc is not None
            else None
        )

        return ActionFormatterInputs(
            setup=setup_snapshot,
            stop_price=stop_price,
            days_to_earnings=days_to_earnings,
            next_earnings_iso=next_earnings_iso,
            option_already_supplied=option_already_supplied,
            option_data_requested=option_data_requested,
        )

    # ------------------------------------------------------------ persistence

    def _persist(
        self,
        db: Session,
        package: ActionPackage,
        snapshot_date: date,
    ) -> ActionSuggestion:
        existing = (
            db.query(ActionSuggestion)
            .filter(ActionSuggestion.symbol == package.symbol)
            .filter(ActionSuggestion.snapshot_date == snapshot_date)
            .one_or_none()
        )

        values = {
            "final_action_label": package.final_action_label,
            "instrument_scope": package.instrument_scope,
            "lifecycle_state": package.lifecycle_state,
            "option_expression_status": package.option_expression_status,
            "manual_option_input_needed": bool(package.manual_option_input_needed),
            "priority_score": package.priority_score,
            "confidence_score": package.confidence_score,
            "suggested_action_summary": package.suggested_action_summary,
            "confidence_breakdown_json": package.confidence_breakdown,
            "entry_condition_json": package.entry_condition.to_dict(),
            "option_contract_criteria_json": (
                package.option_contract_criteria.to_dict()
                if package.option_contract_criteria is not None
                else None
            ),
            "invalidation_condition_json": package.invalidation_condition.to_dict(),
            "upgrade_condition_json": package.upgrade_condition.to_dict(),
            "downgrade_condition_json": package.downgrade_condition.to_dict(),
            "watch_condition_json": package.watch_condition.to_dict(),
            "next_review_trigger_json": package.next_review_trigger.to_dict(),
            "decision_trace_json": list(package.decision_trace),
            "version_stamp_json": dict(package.version_stamp),
            "action_items_json": list(package.action_items),
            "profile_name": package.profile_name,
            "profile_version": package.profile_version,
        }

        if existing is None:
            row = ActionSuggestion(
                symbol=package.symbol,
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


# Helper so unit tests can map the final label without instantiating the
# service.
_ = lifecycle_state_for


__all__ = ["ActionEvaluation", "ActionSuggestionService"]
