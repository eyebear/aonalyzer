"""Phase 21 — DB-facing orchestration for the decision intelligence layer.

Loads the Phase 19 ``DataSufficiencyGate`` output, the Phase 20
``HardFilterService`` output, the auxiliary event/memory inputs, and
calls ``final_decision_builder.build_final_decision``. When persistence
is requested, the snapshot is upserted into ``decision_snapshots``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.common.service_utils import ensure_tables
from app.core.config import AppSettings, get_settings
from app.data_quality.data_sufficiency_gate import DataSufficiencyGate
from app.database.models import Event
from app.decision.decision_models import DecisionSnapshot
from app.decision.event_risk_decision import EventRiskInputs
from app.decision.final_decision_builder import FinalDecision, build_final_decision
from app.decision.memory_risk_decision import MemoryRiskInputs
from app.decision.stock_thesis_decision import StockThesisInputs
from app.earnings.earnings_models import EarningsRiskSnapshot
from app.hard_filter.hard_filter_service import HardFilterService
from app.iv_history.iv_models import IvRiskSnapshot
from app.options.manual_option_input_service import ManualOptionInputService
from app.options.manual_option_models import ManualOptionSnapshotRecord
from app.profiles.profile_manager import profile_manager
from app.profiles.profile_models import StrategyProfile
from app.quant.stock_setup_models import StockSetup


@dataclass
class DecisionEvaluation:
    decision: FinalDecision
    record: DecisionSnapshot | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision.to_dict(),
            "record_id": self.record.id if self.record is not None else None,
        }


class DecisionService:
    def __init__(
        self,
        settings: AppSettings | None = None,
        sufficiency_gate: DataSufficiencyGate | None = None,
        hard_filter_service: HardFilterService | None = None,
        manual_option_service: ManualOptionInputService | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.sufficiency_gate = sufficiency_gate or DataSufficiencyGate()
        self.hard_filter_service = hard_filter_service or HardFilterService(
            settings=self.settings
        )
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
    ) -> DecisionEvaluation:
        self.ensure_tables(db)
        clean = (symbol or "").strip().upper()
        if not clean:
            raise ValueError("symbol is required")

        active_profile = profile or self._safe_profile()

        # Phase 19 sufficiency.
        sufficiency = self.sufficiency_gate.evaluate_symbol(
            db=db,
            symbol=clean,
            option_data_requested=option_data_requested,
            profile=active_profile,
        )

        # Phase 20 hard filter (no persist from here -- the decision service
        # is the single source of persistence for Phase 21; the hard-filter
        # service stays available as its own endpoint).
        option_snapshot: ManualOptionSnapshotRecord | None = None
        if manual_option_snapshot_id is not None:
            option_snapshot = self.manual_option_service.get_manual_snapshot_by_id(
                db=db, snapshot_id=manual_option_snapshot_id
            )
            if option_snapshot is None:
                raise ValueError(
                    f"Manual option snapshot {manual_option_snapshot_id} was not found."
                )
        hard_filter_eval = self.hard_filter_service.evaluate_symbol(
            db=db,
            symbol=clean,
            option_snapshot=option_snapshot,
            profile=active_profile,
            persist=False,
        )
        hard_filter = hard_filter_eval.decision

        # Pull auxiliary context.
        setup = self._latest_setup(db, clean)
        thesis_inputs = StockThesisInputs(
            direction=setup.direction if setup else None,
            current_close=setup.current_close if setup else None,
            entry_zone_low=setup.entry_zone_low if setup else None,
            entry_zone_high=setup.entry_zone_high if setup else None,
        )
        event_risk_inputs = self._build_event_risk_inputs(
            db=db, symbol=clean, option_snapshot=option_snapshot
        )
        memory_risk_inputs = self._build_memory_risk_inputs(db=db, symbol=clean)

        decision = build_final_decision(
            symbol=clean,
            snapshot_date=setup.snapshot_date if setup else None,
            sufficiency=sufficiency,
            hard_filter=hard_filter,
            thesis_inputs=thesis_inputs,
            event_risk_inputs=event_risk_inputs,
            memory_risk_inputs=memory_risk_inputs,
            option_data_requested=option_data_requested,
            profile=active_profile,
            db=db,
        )

        record: DecisionSnapshot | None = None
        if persist:
            snapshot_date = decision.snapshot_date or date.today()
            record = self._persist(
                db=db,
                decision=decision,
                snapshot_date=snapshot_date,
                option_data_requested=option_data_requested,
            )

        return DecisionEvaluation(decision=decision, record=record)

    # ------------------------------------------------------------ db helpers

    def _safe_profile(self) -> StrategyProfile | None:
        try:
            return profile_manager.get_active_profile()
        except Exception:
            return None

    def _latest_setup(self, db: Session, symbol: str) -> StockSetup | None:
        try:
            return (
                db.query(StockSetup)
                .filter(StockSetup.symbol == symbol)
                .order_by(StockSetup.snapshot_date.desc(), StockSetup.id.desc())
                .first()
            )
        except SQLAlchemyError:
            return None

    def _build_event_risk_inputs(
        self,
        db: Session,
        symbol: str,
        option_snapshot: ManualOptionSnapshotRecord | None,
    ) -> EventRiskInputs:
        # Earnings risk snapshot
        earnings: EarningsRiskSnapshot | None = (
            db.query(EarningsRiskSnapshot)
            .filter(EarningsRiskSnapshot.symbol == symbol)
            .order_by(
                EarningsRiskSnapshot.snapshot_date.desc(),
                EarningsRiskSnapshot.id.desc(),
            )
            .first()
        )

        # IV state -- read the latest IV risk snapshot if available.
        iv_state: str | None = None
        try:
            iv: IvRiskSnapshot | None = (
                db.query(IvRiskSnapshot)
                .filter(IvRiskSnapshot.symbol == symbol)
                .order_by(
                    IvRiskSnapshot.snapshot_date.desc(),
                    IvRiskSnapshot.id.desc(),
                )
                .first()
            )
        except SQLAlchemyError:
            iv = None
        if iv is not None:
            iv_state = self._classify_iv_state(iv)

        # Fall back to the option snapshot's IV if no IV risk snapshot
        # exists (the gate still wants a usable state).
        if iv_state is None and option_snapshot is not None:
            iv_state = self._classify_iv_state_from_option(option_snapshot)

        # News -- count high-importance recent events.
        try:
            high_count = (
                db.query(Event)
                .filter(Event.symbol == symbol)
                .filter(Event.importance_level.in_(["HIGH", "high", "High"]))
                .count()
            )
            news_available = (
                db.query(Event).filter(Event.symbol == symbol).count() > 0
            )
        except SQLAlchemyError:
            high_count = 0
            news_available = False

        return EventRiskInputs(
            earnings_risk_label=earnings.risk_label if earnings else None,
            earnings_within_window=bool(earnings.earnings_within_window)
            if earnings
            else False,
            earnings_before_expiration=earnings.earnings_before_expiration
            if earnings
            else None,
            iv_state=iv_state,
            high_importance_news_count=int(high_count),
            news_data_available=news_available,
        )

    def _build_memory_risk_inputs(self, db: Session, symbol: str) -> MemoryRiskInputs:
        """Phase 42.10 — derive memory risk from stored case memory.

        Backward-compatible: when no case memory exists for the symbol (the
        default for fresh data and all pre-Phase-41 tests), this returns the
        original ``memory_data_available=False`` input, so the deterministic
        labels, confidence, and priority are unchanged. Memory only ever feeds
        the memory-risk component — it never overrides sufficiency / hard
        filters / the final label.
        """
        try:
            from app.memory.case_memory_models import CaseMemory

            cases = (
                db.query(CaseMemory)
                .filter(CaseMemory.symbol == symbol)
                .all()
            )
        except Exception:
            return MemoryRiskInputs(memory_data_available=False)

        if not cases:
            return MemoryRiskInputs(memory_data_available=False)

        negative_outcomes = {"STOP_HIT", "STOCK_RIGHT_OPTION_WRONG"}
        negative = sum(
            1 for c in cases if (c.outcome_type or "").upper() in negative_outcomes
        )
        share = negative / len(cases)
        return MemoryRiskInputs(
            similar_case_count=len(cases),
            negative_outcome_share=share,
            memory_data_available=True,
        )

    def _classify_iv_state(self, iv: IvRiskSnapshot) -> str | None:
        if iv.iv_reject_threshold is not None and iv.current_iv is not None:
            if iv.current_iv >= iv.iv_reject_threshold:
                return "HIGH"
            if (
                iv.iv_warning_threshold is not None
                and iv.current_iv >= iv.iv_warning_threshold
            ):
                return "ELEVATED"
            return "NORMAL"
        return "UNKNOWN"

    def _classify_iv_state_from_option(
        self, snapshot: ManualOptionSnapshotRecord
    ) -> str | None:
        # The gate's IV bucketing uses ``ELEVATED`` / ``HIGH`` strings from
        # the Phase 15 IV analyzer. Without thresholds available here we
        # only set UNKNOWN; the analyzer-driven state is already captured
        # in the Phase 20 hard-filter outcomes if option data was supplied.
        if snapshot.implied_volatility is None:
            return "UNKNOWN"
        return None

    # ------------------------------------------------------------ persistence

    def _persist(
        self,
        db: Session,
        decision: FinalDecision,
        snapshot_date: date,
        option_data_requested: bool,
    ) -> DecisionSnapshot:
        existing = (
            db.query(DecisionSnapshot)
            .filter(DecisionSnapshot.symbol == decision.symbol)
            .filter(DecisionSnapshot.snapshot_date == snapshot_date)
            .one_or_none()
        )

        values = {
            "final_label": decision.final_label,
            "rationale": decision.rationale,
            "stock_thesis_label": decision.stock_thesis.thesis_label,
            "option_expression_label": decision.option_expression.expression_label,
            "instrument_scope": decision.instrument_scope.scope,
            "event_risk_level": decision.event_risk.risk_level,
            "memory_risk_level": decision.memory_risk.risk_level,
            "priority_score": decision.priority.score,
            "confidence_score": decision.confidence.score,
            "confidence_breakdown_json": decision.confidence.breakdown.to_dict(),
            "checklist_json": [item.to_dict() for item in decision.checklist],
            "trace_json": list(decision.trace),
            "version_stamp_json": decision.version_stamp.to_dict(),
            "sufficiency_decision_json": decision.sufficiency_decision.to_dict(),
            "hard_filter_decision_json": decision.hard_filter_decision.to_dict(),
            "profile_name": decision.profile_name,
            "profile_version": decision.profile_version,
            "option_data_requested": "TRUE" if option_data_requested else "FALSE",
        }

        if existing is None:
            row = DecisionSnapshot(
                symbol=decision.symbol,
                snapshot_date=snapshot_date,
                **values,
            )
            db.add(row)
            db.commit()
            # Governance audit commits internally (expiring instances); refresh
            # the decision row *after* it so the returned row's attributes stay
            # loaded once the session is closed.
            self._write_governance_audit(db, decision, snapshot_date)
            db.refresh(row)
            return row

        for key, value in values.items():
            setattr(existing, key, value)
        db.commit()
        self._write_governance_audit(db, decision, snapshot_date)
        db.refresh(existing)
        return existing

    def _write_governance_audit(
        self, db: Session, decision: FinalDecision, snapshot_date: date
    ) -> None:
        """Phase 46.10 — persist the decision's version stamp for audit.

        Best-effort: a governance write must never break a decision persist.
        """
        try:
            from app.governance.version_service import GovernanceService

            GovernanceService().write_audit(
                db=db,
                symbol=decision.symbol or "",
                snapshot_date=snapshot_date,
                version_stamp=decision.version_stamp.to_dict(),
            )
        except Exception:
            db.rollback()


__all__ = ["DecisionEvaluation", "DecisionService"]
