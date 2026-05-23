"""Phase 21, step 21.13 — Final decision builder.

The pure-function orchestrator: it takes already-computed inputs (the
Phase 19 sufficiency decision, the Phase 20 hard-filter decision, the
event/memory inputs, etc.) and assembles the final decision dataclass.

The DB-facing layer (``decision_service.py``) is responsible for loading
inputs and persisting the result; this module never touches the
database.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.data_quality.data_sufficiency_gate import GateDecision as SufficiencyDecision
from app.decision.action_label_classifier import (
    classify_action_label,
)
from app.decision.confidence_score_engine import (
    ConfidenceScore,
    compute_confidence_score,
)
from app.decision.decision_trace_builder import build_decision_trace
from app.decision.event_risk_decision import (
    EventRiskDecision,
    EventRiskInputs,
    decide_event_risk,
)
from app.decision.instrument_scope_classifier import (
    InstrumentScope,
    classify_instrument_scope,
)
from app.decision.memory_risk_decision import (
    MemoryRiskDecision,
    MemoryRiskInputs,
    decide_memory_risk,
)
from app.decision.opportunity_checklist import (
    ChecklistItem,
    build_opportunity_checklist,
)
from app.decision.option_expression_decision import (
    OptionExpressionDecision,
    decide_option_expression,
)
from app.decision.priority_score_engine import (
    PriorityScore,
    compute_priority_score,
)
from app.decision.stock_thesis_decision import (
    StockThesisDecision,
    StockThesisInputs,
    decide_stock_thesis,
)
from app.decision.version_stamp_builder import VersionStamp, build_version_stamp
from app.hard_filter.hard_filter_gate import HardFilterDecision
from app.profiles.profile_models import StrategyProfile


@dataclass(frozen=True)
class FinalDecision:
    symbol: str | None
    snapshot_date: date | None
    final_label: str
    rationale: str

    stock_thesis: StockThesisDecision
    option_expression: OptionExpressionDecision
    instrument_scope: InstrumentScope
    event_risk: EventRiskDecision
    memory_risk: MemoryRiskDecision

    checklist: list[ChecklistItem]
    priority: PriorityScore
    confidence: ConfidenceScore
    trace: list[dict[str, Any]]
    version_stamp: VersionStamp

    sufficiency_decision: SufficiencyDecision
    hard_filter_decision: HardFilterDecision

    profile_name: str | None = None
    profile_version: str | None = None
    evaluated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "snapshot_date": self.snapshot_date.isoformat()
            if self.snapshot_date is not None
            else None,
            "final_label": self.final_label,
            "rationale": self.rationale,
            "stock_thesis": self.stock_thesis.to_dict(),
            "option_expression": self.option_expression.to_dict(),
            "instrument_scope": self.instrument_scope.to_dict(),
            "event_risk": self.event_risk.to_dict(),
            "memory_risk": self.memory_risk.to_dict(),
            "checklist": [item.to_dict() for item in self.checklist],
            "priority": self.priority.to_dict(),
            "confidence": self.confidence.to_dict(),
            "trace": list(self.trace),
            "version_stamp": self.version_stamp.to_dict(),
            "sufficiency_decision": self.sufficiency_decision.to_dict(),
            "hard_filter_decision": self.hard_filter_decision.to_dict(),
            "profile_name": self.profile_name,
            "profile_version": self.profile_version,
            "evaluated_at": self.evaluated_at.isoformat(),
        }


def build_final_decision(
    *,
    symbol: str | None,
    snapshot_date: date | None,
    sufficiency: SufficiencyDecision,
    hard_filter: HardFilterDecision,
    thesis_inputs: StockThesisInputs | None = None,
    event_risk_inputs: EventRiskInputs | None = None,
    memory_risk_inputs: MemoryRiskInputs | None = None,
    option_data_requested: bool = False,
    profile: StrategyProfile | None = None,
    db: Session | None = None,
    profile_minimum_risk_reward: float | None = None,
) -> FinalDecision:
    thesis_inputs = thesis_inputs or StockThesisInputs()
    event_risk_inputs = event_risk_inputs or EventRiskInputs()
    memory_risk_inputs = memory_risk_inputs or MemoryRiskInputs()

    thesis = decide_stock_thesis(sufficiency, hard_filter, thesis_inputs)
    option_expr = decide_option_expression(hard_filter)
    scope = classify_instrument_scope(
        option_expr, option_data_requested=option_data_requested
    )
    event_risk = decide_event_risk(event_risk_inputs)
    memory_risk = decide_memory_risk(memory_risk_inputs)
    action = classify_action_label(thesis, scope)

    checklist = build_opportunity_checklist(
        sufficiency=sufficiency,
        hard_filter=hard_filter,
        event_risk=event_risk,
        memory_risk=memory_risk,
    )

    minimum_rr = (
        float(profile.minimum_risk_reward)
        if profile is not None
        else (profile_minimum_risk_reward if profile_minimum_risk_reward is not None else 2.0)
    )
    priority = compute_priority_score(
        hard_filter=hard_filter,
        event_risk=event_risk,
        memory_risk=memory_risk,
        setup_direction=thesis_inputs.direction,
        profile_minimum_risk_reward=minimum_rr,
    )
    confidence = compute_confidence_score(
        sufficiency=sufficiency,
        hard_filter=hard_filter,
        event_risk=event_risk,
        memory_risk=memory_risk,
    )
    trace = build_decision_trace(
        sufficiency=sufficiency,
        hard_filter=hard_filter,
        thesis=thesis,
        option_expression=option_expr,
        scope=scope,
        event_risk=event_risk,
        memory_risk=memory_risk,
        final_action=action,
    )
    stamp = build_version_stamp(db=db, profile=profile)

    return FinalDecision(
        symbol=symbol,
        snapshot_date=snapshot_date,
        final_label=action.final_label,
        rationale=action.rationale,
        stock_thesis=thesis,
        option_expression=option_expr,
        instrument_scope=scope,
        event_risk=event_risk,
        memory_risk=memory_risk,
        checklist=checklist,
        priority=priority,
        confidence=confidence,
        trace=trace,
        version_stamp=stamp,
        sufficiency_decision=sufficiency,
        hard_filter_decision=hard_filter,
        profile_name=profile.profile_name if profile is not None else None,
        profile_version=profile.profile_version if profile is not None else None,
    )


__all__ = ["FinalDecision", "build_final_decision"]
