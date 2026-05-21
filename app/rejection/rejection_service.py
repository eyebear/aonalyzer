"""Phase 23 — DB-facing orchestration for the rejection intelligence layer.

Consumes the Phase 22 action package (which already chains Phase 19 ->
20 -> 21 internally), runs the Phase 23 classifier + explainers, and
optionally persists the rejection envelope via
``RejectionMemoryWriter``.

The service intentionally does **not** re-run the upstream gates; it
only enriches and stores. This keeps each phase decoupled.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.action.action_service import ActionEvaluation, ActionSuggestionService
from app.common.service_utils import ensure_tables
from app.core.config import AppSettings, get_settings
from app.decision.final_decision_builder import FinalDecision
from app.options.option_filters import (
    DTE_TOO_SHORT,
    OPTION_TOO_EXPENSIVE,
)
from app.profiles.profile_manager import profile_manager
from app.profiles.profile_models import StrategyProfile
from app.rejection.breakeven_failure_explainer import (
    ReasonPayload,
    explain_breakeven_failures,
)
from app.rejection.iv_earnings_rejection_explainer import (
    explain_iv_earnings_rejections,
)
from app.rejection.liquidity_rejection_explainer import (
    explain_liquidity_rejections,
)
from app.rejection.rejection_categories import (
    CATEGORY_DATA_INSUFFICIENT,
    CATEGORY_HARD_STOCK_REJECTION,
    CATEGORY_NOT_REJECTED,
    REASON_CATEGORY_DATA,
    REASON_CATEGORY_OPTION,
    REASON_CATEGORY_STOCK,
    SOURCE_PHASE_DATA_SUFFICIENCY,
    SOURCE_PHASE_HARD_FILTER,
    SOURCE_PHASE_OPTION_EXPRESSION,
)
from app.rejection.rejection_classifier import (
    RejectionClassification,
    classify_rejection,
)
from app.rejection.rejection_memory_writer import (
    RejectionMemoryWriter,
    WrittenRejection,
)


@dataclass
class RejectionEvaluation:
    classification: RejectionClassification
    reasons: list[ReasonPayload]
    written: WrittenRejection | None = None
    snapshot_date: date | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_date": self.snapshot_date.isoformat()
            if self.snapshot_date is not None
            else None,
            "classification": self.classification.to_dict(),
            "reasons": [r.to_dict() for r in self.reasons],
            "candidate_id": (
                self.written.candidate.id
                if self.written is not None and self.written.candidate is not None
                else None
            ),
            "reason_ids": (
                [r.id for r in self.written.reasons]
                if self.written is not None
                else []
            ),
        }


class RejectionService:
    def __init__(
        self,
        settings: AppSettings | None = None,
        action_service: ActionSuggestionService | None = None,
        memory_writer: RejectionMemoryWriter | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.action_service = action_service or ActionSuggestionService(
            settings=self.settings
        )
        self.memory_writer = memory_writer or RejectionMemoryWriter()

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
    ) -> RejectionEvaluation:
        self.ensure_tables(db)
        clean = (symbol or "").strip().upper()
        if not clean:
            raise ValueError("symbol is required")

        active_profile = profile or self._safe_profile()

        # Run the Phase 22 layer (which runs Phase 19/20/21 internally). The
        # action service is invoked with persist=False to keep this entry
        # point side-effect-free unless ``persist`` is requested.
        action_eval: ActionEvaluation = self.action_service.evaluate_symbol(
            db=db,
            symbol=clean,
            manual_option_snapshot_id=manual_option_snapshot_id,
            option_data_requested=option_data_requested,
            persist=False,
            profile=active_profile,
        )
        package = action_eval.package
        # Reconstruct the FinalDecision from the package's underlying
        # references. ``ActionSuggestionService`` already builds its package
        # from a fresh ``FinalDecision``; we ask for it via the service to
        # avoid re-running upstream gates.
        decision: FinalDecision = self._reconstruct_decision(
            db=db,
            clean=clean,
            manual_option_snapshot_id=manual_option_snapshot_id,
            option_data_requested=option_data_requested,
            profile=active_profile,
        )

        classification = classify_rejection(
            decision,
            profile_minimum_risk_reward=(
                float(active_profile.minimum_risk_reward)
                if active_profile is not None
                else None
            ),
        )

        reasons = _collect_reasons(decision, classification=classification)

        snapshot_date = decision.snapshot_date

        written: WrittenRejection | None = None
        if persist and snapshot_date is not None:
            written = self.memory_writer.write(
                db=db,
                symbol=clean,
                snapshot_date=snapshot_date,
                classification=classification,
                lifecycle_state=package.lifecycle_state,
                reason_payloads=reasons,
                profile_name=package.profile_name,
                profile_version=package.profile_version,
            )

        return RejectionEvaluation(
            classification=classification,
            reasons=reasons,
            written=written,
            snapshot_date=snapshot_date,
        )

    # ----------------------------------------------------------- helpers

    def _safe_profile(self) -> StrategyProfile | None:
        try:
            return profile_manager.get_active_profile()
        except Exception:
            return None

    def _reconstruct_decision(
        self,
        *,
        db: Session,
        clean: str,
        manual_option_snapshot_id: int | None,
        option_data_requested: bool,
        profile: StrategyProfile | None,
    ) -> FinalDecision:
        """Reuse the action service's decision_service so any injected
        dependencies (fake manual-option service, test profile, etc.)
        propagate end-to-end. Phase 19-21 are idempotent so the second
        invocation is inexpensive."""
        evaluation = self.action_service.decision_service.evaluate_symbol(
            db=db,
            symbol=clean,
            manual_option_snapshot_id=manual_option_snapshot_id,
            option_data_requested=option_data_requested,
            persist=False,
            profile=profile,
        )
        return evaluation.decision


def _collect_reasons(
    decision: FinalDecision,
    *,
    classification: RejectionClassification,
) -> list[ReasonPayload]:
    """Bundle the per-explainer outputs into a single ordered list.

    For ``NOT_REJECTED`` classifications we still return an empty list so
    the writer's contract stays uniform.
    """
    if classification.rejection_category == CATEGORY_NOT_REJECTED:
        return []

    reasons: list[ReasonPayload] = []

    # Data sufficiency blocks (e.g. INSUFFICIENT_PRICE_HISTORY).
    if classification.rejection_category == CATEGORY_DATA_INSUFFICIENT:
        for label in decision.sufficiency_decision.blocking_labels or []:
            reasons.append(
                ReasonPayload(
                    reason_label=label,
                    reason_category=REASON_CATEGORY_DATA,
                    source_phase=SOURCE_PHASE_DATA_SUFFICIENCY,
                    explanation=(
                        f"Data sufficiency gate reported '{label}'; cannot "
                        "evaluate the candidate yet."
                    ),
                    context={},
                )
            )
        return _dedupe(reasons)

    # Hard stock rejection -- enumerate stock blocking labels from Phase 20.
    if classification.rejection_category == CATEGORY_HARD_STOCK_REJECTION:
        for outcome in decision.hard_filter_decision.outcomes:
            if outcome.category != "stock" or outcome.status != "FAIL":
                continue
            reasons.append(
                ReasonPayload(
                    reason_label=outcome.label or outcome.name,
                    reason_category=REASON_CATEGORY_STOCK,
                    source_phase=SOURCE_PHASE_HARD_FILTER,
                    explanation=outcome.detail
                    or f"Stock-side hard filter '{outcome.name}' failed.",
                    context={"value": outcome.value, "filter_name": outcome.name},
                )
            )

    # Option-only rejections (STOCK_OK_OPTION_BAD): pull through the
    # dedicated explainers. We also fold in any non-breakeven option
    # failures not covered by the explainers (e.g. DTE_TOO_SHORT,
    # OPTION_TOO_EXPENSIVE) so the user sees the complete picture.
    breakeven = explain_breakeven_failures(decision)
    iv_earnings = explain_iv_earnings_rejections(decision)
    liquidity = explain_liquidity_rejections(decision)
    reasons.extend(breakeven)
    reasons.extend(iv_earnings)
    reasons.extend(liquidity)

    # Catch-all for option failures not handled by the explainers above.
    explained_labels = {p.reason_label for p in (breakeven + iv_earnings + liquidity)}
    for outcome in decision.hard_filter_decision.outcomes:
        if outcome.category != "option" or outcome.status != "FAIL":
            continue
        label = outcome.label or ""
        if label in explained_labels:
            continue
        # Only emit for option-only or stock-OK-option-bad rejections; for
        # a hard stock rejection the option failure is incidental noise.
        if classification.rejection_category not in {
            "STOCK_OK_OPTION_BAD",
            CATEGORY_HARD_STOCK_REJECTION,
        }:
            continue
        # Map a couple of known labels to friendlier explanations.
        explanation = outcome.detail or f"Option-side hard filter '{outcome.name}' failed."
        if label == DTE_TOO_SHORT:
            explanation = (
                "Days-to-expiration is below the profile minimum; the "
                "contract expires too soon."
            )
        elif label == OPTION_TOO_EXPENSIVE:
            explanation = (
                "Contract cost is above the profile's premium budget."
            )
        reasons.append(
            ReasonPayload(
                reason_label=label or outcome.name,
                reason_category=REASON_CATEGORY_OPTION,
                source_phase=SOURCE_PHASE_OPTION_EXPRESSION,
                explanation=explanation,
                context={"value": outcome.value, "filter_name": outcome.name},
            )
        )

    return _dedupe(reasons)


def _dedupe(reasons: list[ReasonPayload]) -> list[ReasonPayload]:
    seen: set[tuple[str, str]] = set()
    out: list[ReasonPayload] = []
    for r in reasons:
        key = (r.reason_label, r.source_phase)
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


__all__ = ["RejectionEvaluation", "RejectionService"]
