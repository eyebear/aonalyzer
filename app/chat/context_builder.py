"""Phase 37, step 37.2 — chat context builder.

Assembles a deterministic ``ChatContext`` for a symbol from the canonical
decision/action services plus persisted auxiliary records. The context is the
ONLY ground truth the chat may use; it honestly records the option-data status
(NOT_AVAILABLE / INCOMPLETE / AVAILABLE) so the chat can never invent missing
option values.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.action.action_service import ActionSuggestionService
from app.core.config import AppSettings, get_settings
from app.database.models import Event
from app.decision.decision_service import DecisionService
from app.earnings.earnings_models import EarningsRiskSnapshot
from app.iv_history.iv_models import IvRiskSnapshot
from app.options.manual_option_input_service import ManualOptionInputService

OPTION_DATA_NOT_AVAILABLE = "OPTION_DATA_NOT_AVAILABLE"
OPTION_DATA_INCOMPLETE = "OPTION_DATA_INCOMPLETE"
OPTION_DATA_AVAILABLE = "OPTION_DATA_AVAILABLE"


@dataclass
class ChatContext:
    symbol: str | None
    final_action_label: str | None = None
    rationale: str | None = None
    stock_thesis: dict[str, Any] | None = None
    option_expression: dict[str, Any] | None = None
    option_data_status: str = OPTION_DATA_NOT_AVAILABLE
    has_manual_snapshot: bool = False
    manual_option: dict[str, Any] | None = None
    missing_option_fields: list[str] = field(default_factory=list)
    hard_filter_decision: dict[str, Any] | None = None
    decision_trace: list[dict[str, Any]] = field(default_factory=list)
    confidence: dict[str, Any] | None = None
    priority_score: float | None = None
    events: list[dict[str, Any]] = field(default_factory=list)
    earnings: dict[str, Any] | None = None
    iv: dict[str, Any] | None = None
    similar_cases: list[dict[str, Any]] = field(default_factory=list)
    version_stamp: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "final_action_label": self.final_action_label,
            "rationale": self.rationale,
            "stock_thesis": self.stock_thesis,
            "option_expression": self.option_expression,
            "option_data_status": self.option_data_status,
            "has_manual_snapshot": self.has_manual_snapshot,
            "manual_option": self.manual_option,
            "missing_option_fields": list(self.missing_option_fields),
            "hard_filter_decision": self.hard_filter_decision,
            "decision_trace": list(self.decision_trace),
            "confidence": self.confidence,
            "priority_score": self.priority_score,
            "events": list(self.events),
            "earnings": self.earnings,
            "iv": self.iv,
            "similar_cases": list(self.similar_cases),
            "version_stamp": dict(self.version_stamp),
        }


class ChatContextBuilder:
    def __init__(
        self,
        settings: AppSettings | None = None,
        decision_service: DecisionService | None = None,
        action_service: ActionSuggestionService | None = None,
        manual_option_service: ManualOptionInputService | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.decision_service = decision_service or DecisionService(settings=self.settings)
        self.action_service = action_service or ActionSuggestionService(
            settings=self.settings, decision_service=self.decision_service
        )
        self.manual_option_service = manual_option_service or ManualOptionInputService()

    def build(
        self,
        db: Session,
        symbol: str,
        *,
        manual_option_snapshot_id: int | None = None,
        option_data_requested: bool = False,
    ) -> ChatContext:
        clean = (symbol or "").strip().upper()
        if not clean:
            return ChatContext(symbol=None)

        has_manual_snapshot = manual_option_snapshot_id is not None
        if has_manual_snapshot:
            option_data_requested = True

        manual_record = None
        if has_manual_snapshot:
            try:
                manual_record = self.manual_option_service.get_manual_snapshot_by_id(
                    db=db, snapshot_id=manual_option_snapshot_id
                )
            except Exception:
                manual_record = None

        option_status, missing_fields, manual_dict = self._option_status(manual_record)

        try:
            decision = self.decision_service.evaluate_symbol(
                db=db,
                symbol=clean,
                manual_option_snapshot_id=manual_option_snapshot_id,
                option_data_requested=option_data_requested,
                persist=False,
            ).decision
            package = self.action_service.evaluate_symbol(
                db=db,
                symbol=clean,
                manual_option_snapshot_id=manual_option_snapshot_id,
                option_data_requested=option_data_requested,
                persist=False,
            ).package
        except Exception:
            decision = None
            package = None

        ctx = ChatContext(symbol=clean)
        ctx.option_data_status = option_status
        ctx.has_manual_snapshot = has_manual_snapshot and manual_record is not None
        ctx.manual_option = manual_dict
        ctx.missing_option_fields = missing_fields

        if decision is not None:
            ctx.final_action_label = decision.final_label
            ctx.rationale = decision.rationale
            ctx.stock_thesis = decision.stock_thesis.to_dict()
            ctx.option_expression = decision.option_expression.to_dict()
            ctx.hard_filter_decision = decision.hard_filter_decision.to_dict()
            ctx.decision_trace = list(decision.trace)
            ctx.confidence = decision.confidence.breakdown.to_dict()
            ctx.priority_score = decision.priority.score
            ctx.version_stamp = decision.version_stamp.to_dict()
        if package is not None:
            ctx.final_action_label = package.final_action_label

        ctx.events = self._recent_events(db, clean)
        ctx.earnings = self._latest_earnings(db, clean)
        ctx.iv = self._latest_iv(db, clean)
        ctx.similar_cases = self._similar_cases(db, clean)
        return ctx

    # --------------------------------------------------------- option status

    def _option_status(
        self, manual_record: Any | None
    ) -> tuple[str, list[str], dict[str, Any] | None]:
        if manual_record is None:
            return OPTION_DATA_NOT_AVAILABLE, [], None
        missing = list(getattr(manual_record, "missing_fields", []) or [])
        quality = getattr(manual_record, "data_quality_status", None)
        manual_dict = manual_record.to_dict()
        if quality == "OPTION_TEXT_PARSED":
            return OPTION_DATA_AVAILABLE, missing, manual_dict
        if quality == "OPTION_DATA_NOT_AVAILABLE":
            return OPTION_DATA_NOT_AVAILABLE, missing, manual_dict
        # INSUFFICIENT_OPTION_DATA or any partial state.
        return OPTION_DATA_INCOMPLETE, missing, manual_dict

    # --------------------------------------------------------- aux readers

    def _recent_events(self, db: Session, symbol: str, limit: int = 5) -> list[dict[str, Any]]:
        try:
            rows = (
                db.query(Event)
                .filter(Event.symbol == symbol)
                .order_by(Event.event_time.desc(), Event.id.desc())
                .limit(limit)
                .all()
            )
        except SQLAlchemyError:
            return []
        return [
            {
                "id": r.id,
                "event_type": r.event_type,
                "importance_level": r.importance_level,
                "headline": r.headline or r.source_title,
            }
            for r in rows
        ]

    def _latest_earnings(self, db: Session, symbol: str) -> dict[str, Any] | None:
        try:
            row = (
                db.query(EarningsRiskSnapshot)
                .filter(EarningsRiskSnapshot.symbol == symbol)
                .order_by(EarningsRiskSnapshot.snapshot_date.desc(), EarningsRiskSnapshot.id.desc())
                .first()
            )
        except SQLAlchemyError:
            return None
        if row is None:
            return None
        return {
            "days_to_earnings": row.days_to_earnings,
            "risk_label": row.risk_label,
            "earnings_within_window": bool(row.earnings_within_window),
        }

    def _latest_iv(self, db: Session, symbol: str) -> dict[str, Any] | None:
        try:
            row = (
                db.query(IvRiskSnapshot)
                .filter(IvRiskSnapshot.symbol == symbol)
                .order_by(IvRiskSnapshot.snapshot_date.desc(), IvRiskSnapshot.id.desc())
                .first()
            )
        except SQLAlchemyError:
            return None
        if row is None or (
            row.current_iv is None and row.iv_rank is None and row.iv_percentile is None
        ):
            return None
        return {
            "current_iv": row.current_iv,
            "iv_rank": row.iv_rank,
            "risk_label": row.risk_label,
        }

    def _similar_cases(self, db: Session, symbol: str) -> list[dict[str, Any]]:
        from app.chat.memory_retriever import retrieve_similar_cases

        return retrieve_similar_cases(db, symbol)


__all__ = [
    "OPTION_DATA_AVAILABLE",
    "OPTION_DATA_INCOMPLETE",
    "OPTION_DATA_NOT_AVAILABLE",
    "ChatContext",
    "ChatContextBuilder",
]
