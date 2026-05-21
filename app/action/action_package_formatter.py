"""Phase 22, step 22.12 — Action package formatter.

The single point that produces the Phase 22 final action package from
the Phase 21 ``FinalDecision`` and the persisted upstream rows. Pure
function: no DB I/O. Returns an ``ActionPackage`` dataclass whose
``.to_dict()`` matches the field list in the Phase 22 outline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.action.action_labels import lifecycle_state_for
from app.action.downgrade_condition_builder import (
    DowngradeCondition,
    build_downgrade_condition,
)
from app.action.entry_condition_builder import (
    EntryCondition,
    StockSetupSnapshot,
    build_entry_condition,
)
from app.action.invalidation_condition_builder import (
    InvalidationCondition,
    build_invalidation_condition,
)
from app.action.manual_option_input_action_builder import (
    ManualOptionInputAction,
    build_manual_option_input_action,
)
from app.action.next_review_trigger_builder import (
    NextReviewTrigger,
    build_next_review_trigger,
)
from app.action.option_contract_criteria_builder import (
    OptionContractCriteria,
    build_option_contract_criteria,
)
from app.action.action_items_generator import generate_action_items
from app.action.suggested_action_summary import build_suggested_action_summary
from app.action.upgrade_condition_builder import (
    UpgradeCondition,
    build_upgrade_condition,
)
from app.action.watch_condition_builder import (
    WatchCondition,
    build_watch_condition,
)
from app.core.config import AppSettings
from app.decision.final_decision_builder import FinalDecision
from app.profiles.profile_models import StrategyProfile


@dataclass(frozen=True)
class ActionPackage:
    symbol: str | None
    final_action_label: str
    instrument_scope: str
    lifecycle_state: str
    priority_score: float
    confidence_score: float
    confidence_breakdown: dict[str, Any]
    suggested_action_summary: str
    entry_condition: EntryCondition
    option_expression_status: str
    option_contract_criteria: OptionContractCriteria | None
    manual_option_input_needed: bool
    invalidation_condition: InvalidationCondition
    upgrade_condition: UpgradeCondition
    downgrade_condition: DowngradeCondition
    watch_condition: WatchCondition
    next_review_trigger: NextReviewTrigger
    decision_trace: list[dict[str, Any]]
    version_stamp: dict[str, Any]
    action_items: list[dict[str, Any]] = field(default_factory=list)
    profile_name: str | None = None
    profile_version: str | None = None
    evaluated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "final_action_label": self.final_action_label,
            "instrument_scope": self.instrument_scope,
            "lifecycle_state": self.lifecycle_state,
            "priority_score": self.priority_score,
            "confidence_score": self.confidence_score,
            "confidence_breakdown": self.confidence_breakdown,
            "suggested_action_summary": self.suggested_action_summary,
            "entry_condition": self.entry_condition.to_dict(),
            "option_expression_status": self.option_expression_status,
            "option_contract_criteria": (
                self.option_contract_criteria.to_dict()
                if self.option_contract_criteria is not None
                else None
            ),
            "manual_option_input_needed": self.manual_option_input_needed,
            "invalidation_condition": self.invalidation_condition.to_dict(),
            "upgrade_condition": self.upgrade_condition.to_dict(),
            "downgrade_condition": self.downgrade_condition.to_dict(),
            "watch_condition": self.watch_condition.to_dict(),
            "next_review_trigger": self.next_review_trigger.to_dict(),
            "decision_trace": list(self.decision_trace),
            "version_stamp": dict(self.version_stamp),
            "action_items": list(self.action_items),
            "profile_name": self.profile_name,
            "profile_version": self.profile_version,
            "evaluated_at": self.evaluated_at.isoformat(),
        }


@dataclass(frozen=True)
class ActionFormatterInputs:
    """Extra inputs the formatter needs beyond ``FinalDecision`` itself."""

    setup: StockSetupSnapshot = field(default_factory=StockSetupSnapshot)
    stop_price: float | None = None
    days_to_earnings: int | None = None
    next_earnings_iso: str | None = None
    option_already_supplied: bool = False
    option_data_requested: bool = False


def format_action_package(
    decision: FinalDecision,
    inputs: ActionFormatterInputs | None = None,
    *,
    profile: StrategyProfile | None = None,
    settings: AppSettings | None = None,
) -> ActionPackage:
    inputs = inputs or ActionFormatterInputs()

    lifecycle = lifecycle_state_for(decision.final_label)
    warnings = list(decision.hard_filter_decision.warning_labels or [])

    summary = build_suggested_action_summary(decision)

    entry = build_entry_condition(setup=inputs.setup, lifecycle_state=lifecycle)

    option_criteria = build_option_contract_criteria(
        profile=profile,
        settings=settings,
        direction=inputs.setup.direction,
        final_label=decision.final_label,
        option_data_requested=inputs.option_data_requested,
        option_already_supplied=inputs.option_already_supplied,
    )

    manual_option = build_manual_option_input_action(
        final_label=decision.final_label,
        option_data_requested=inputs.option_data_requested,
        option_already_supplied=inputs.option_already_supplied,
        criteria=option_criteria,
        symbol=decision.symbol,
    )

    invalidation = build_invalidation_condition(
        setup=inputs.setup,
        stop_price=inputs.stop_price,
        nearest_support=inputs.setup.nearest_support,
        nearest_resistance=inputs.setup.nearest_resistance,
        warning_labels=warnings,
    )

    upgrade = build_upgrade_condition(
        lifecycle_state=lifecycle,
        warning_labels=warnings,
        entry_zone_low=inputs.setup.entry_zone_low,
        entry_zone_high=inputs.setup.entry_zone_high,
    )

    downgrade = build_downgrade_condition(
        lifecycle_state=lifecycle,
        warning_labels=warnings,
        stop_price=inputs.stop_price,
        direction=inputs.setup.direction,
    )

    watch = build_watch_condition(
        lifecycle_state=lifecycle,
        entry_zone_low=inputs.setup.entry_zone_low,
        entry_zone_high=inputs.setup.entry_zone_high,
        warning_labels=warnings,
        next_earnings_iso=inputs.next_earnings_iso,
    )

    next_review = build_next_review_trigger(
        lifecycle_state=lifecycle,
        profile=profile,
        days_to_earnings=inputs.days_to_earnings,
    )

    action_items = generate_action_items(
        sufficiency=decision.sufficiency_decision,
        manual_option_input=manual_option,
        lifecycle_state=lifecycle,
        symbol=decision.symbol,
    )

    return ActionPackage(
        symbol=decision.symbol,
        final_action_label=decision.final_label,
        instrument_scope=decision.instrument_scope.scope,
        lifecycle_state=lifecycle,
        priority_score=decision.priority.score,
        confidence_score=decision.confidence.score,
        confidence_breakdown=decision.confidence.breakdown.to_dict(),
        suggested_action_summary=summary,
        entry_condition=entry,
        option_expression_status=decision.option_expression.expression_label,
        option_contract_criteria=option_criteria,
        manual_option_input_needed=manual_option.needed,
        invalidation_condition=invalidation,
        upgrade_condition=upgrade,
        downgrade_condition=downgrade,
        watch_condition=watch,
        next_review_trigger=next_review,
        decision_trace=list(decision.trace),
        version_stamp=decision.version_stamp.to_dict(),
        action_items=action_items,
        profile_name=decision.profile_name,
        profile_version=decision.profile_version,
    )


__all__ = ["ActionFormatterInputs", "ActionPackage", "format_action_package"]
