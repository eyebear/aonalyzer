"""Phase 45, steps 45.2-45.8 / 45.12 — improvement engine.

Generates explainable, approval-gated improvement suggestions from recorded
outcomes (never applying them). Covers DTE, IV threshold, breakeven margin,
manual-option-prompt, do-not-touch, and override-based suggestions. Approval is
an explicit, separate step.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.common.service_utils import ensure_tables
from app.learning.improvement_models import (
    STATUS_APPROVED,
    STATUS_PROPOSED,
    STATUS_REJECTED,
    SUGGEST_BREAKEVEN_MARGIN,
    SUGGEST_DO_NOT_TOUCH,
    SUGGEST_IV_THRESHOLD,
    SUGGEST_MANUAL_OPTION_PROMPT,
    SUGGEST_OVERRIDE_BASED,
    ImprovementSuggestion,
)
from app.learning.rejection_outcome_models import (
    SOURCE_DO_NOT_TOUCH,
    SOURCE_REJECTION,
    RejectionOutcome,
)
from app.memory.case_memory_models import CASE_STOCK_RIGHT_OPTION_WRONG, CaseMemory
from app.user_actions.user_action_models import OverrideOutcome

# Thresholds that turn an observed rate into a suggestion. Conservative on
# purpose: a few data points should not trigger a rule-change proposal.
MIN_SAMPLE = 5
SROW_RATE_THRESHOLD = 0.4
TOO_STRICT_RATE_THRESHOLD = 0.5
MISSED_RATE_THRESHOLD = 0.5


@dataclass
class ImprovementRunResult:
    suggestions_created: int = 0
    suggestions_existing: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "suggestions_created": self.suggestions_created,
            "suggestions_existing": self.suggestions_existing,
        }


class ImprovementEngine:
    def ensure_tables(self, db: Session) -> None:
        ensure_tables(db)

    def generate(self, db: Session) -> ImprovementRunResult:
        self.ensure_tables(db)
        result = ImprovementRunResult()
        for proposal in self._proposals(db):
            created = self._upsert_proposed(db, proposal)
            if created:
                result.suggestions_created += 1
            else:
                result.suggestions_existing += 1
        db.commit()
        return result

    def _proposals(self, db: Session) -> list[dict[str, Any]]:
        proposals: list[dict[str, Any]] = []

        # 45.4/45.5 — stock-right/option-wrong is high -> tighten IV + breakeven.
        srow = db.query(CaseMemory).filter(
            CaseMemory.case_type == CASE_STOCK_RIGHT_OPTION_WRONG
        ).count()
        total_cases = db.query(CaseMemory).count()
        if total_cases >= MIN_SAMPLE and srow / total_cases >= SROW_RATE_THRESHOLD:
            proposals.append(
                {
                    "suggestion_type": SUGGEST_BREAKEVEN_MARGIN,
                    "title": "Increase minimum target-vs-breakeven margin",
                    "rationale": (
                        f"{srow}/{total_cases} cases were stock-right/option-wrong. "
                        "A larger breakeven margin would screen out options that "
                        "fail despite a correct stock thesis."
                    ),
                    "current_value": "profile.minimum_target_breakeven_margin_percent",
                    "proposed_value": "increase by ~2-3 percentage points",
                    "evidence": {"stock_right_option_wrong": srow, "total_cases": total_cases},
                }
            )
            proposals.append(
                {
                    "suggestion_type": SUGGEST_IV_THRESHOLD,
                    "title": "Lower IV reject threshold",
                    "rationale": (
                        "Repeated stock-right/option-wrong outcomes suggest options "
                        "were too expensive; a lower IV reject threshold avoids them."
                    ),
                    "current_value": "profile.iv_reject_threshold",
                    "proposed_value": "lower by ~5 points",
                    "evidence": {"stock_right_option_wrong": srow},
                }
            )

        # 45.6 — many incomplete manual options -> improve the paste prompt.
        # (Heuristic placeholder: surfaced when option-wrong cases accumulate.)
        if srow >= MIN_SAMPLE:
            proposals.append(
                {
                    "suggestion_type": SUGGEST_MANUAL_OPTION_PROMPT,
                    "title": "Strengthen the manual option paste prompt",
                    "rationale": (
                        "Clarify which fields (IV, Greeks, bid/ask) most affect "
                        "suitability so pasted contracts are more complete."
                    ),
                    "current_value": "default paste prompt",
                    "proposed_value": "add field-importance guidance",
                    "evidence": {"stock_right_option_wrong": srow},
                }
            )

        # 45.7 — rejections / freezes too strict -> loosen.
        rejections = db.query(RejectionOutcome).all()
        rej = [r for r in rejections if r.source_type == SOURCE_REJECTION]
        dnt = [r for r in rejections if r.source_type == SOURCE_DO_NOT_TOUCH]
        if len(rej) >= MIN_SAMPLE:
            too_strict = sum(1 for r in rej if r.is_too_strict) / len(rej)
            if too_strict >= TOO_STRICT_RATE_THRESHOLD:
                proposals.append(
                    {
                        "suggestion_type": SUGGEST_OVERRIDE_BASED,
                        "title": "Loosen rejection rule (too strict)",
                        "rationale": (
                            f"{too_strict:.0%} of rejections were too strict — the "
                            "rejected stocks advanced. Consider relaxing the rule."
                        ),
                        "current_value": "profile.minimum_risk_reward",
                        "proposed_value": "lower slightly",
                        "evidence": {"too_strict_rate": round(too_strict, 4), "sample": len(rej)},
                    }
                )
        if len(dnt) >= MIN_SAMPLE:
            dnt_too_strict = sum(1 for r in dnt if r.is_too_strict) / len(dnt)
            if dnt_too_strict >= TOO_STRICT_RATE_THRESHOLD:
                proposals.append(
                    {
                        "suggestion_type": SUGGEST_DO_NOT_TOUCH,
                        "title": "Shorten do-not-touch freeze window",
                        "rationale": (
                            f"{dnt_too_strict:.0%} of freezes were too strict. A "
                            "shorter freeze window would release opportunities sooner."
                        ),
                        "current_value": "freeze window days",
                        "proposed_value": "reduce window",
                        "evidence": {
                            "too_strict_rate": round(dnt_too_strict, 4),
                            "sample": len(dnt),
                        },
                    }
                )

        # 45.8 — override-based: many missed opportunities -> system too cautious.
        overrides = db.query(OverrideOutcome).all()
        if len(overrides) >= MIN_SAMPLE:
            missed = sum(1 for o in overrides if o.is_missed_opportunity) / len(overrides)
            if missed >= MISSED_RATE_THRESHOLD:
                proposals.append(
                    {
                        "suggestion_type": SUGGEST_OVERRIDE_BASED,
                        "title": "Recommendations ignored often turned out to be winners",
                        "rationale": (
                            f"{missed:.0%} of ignored recommendations rose. Consider "
                            "surfacing these candidates more prominently."
                        ),
                        "current_value": "candidate prominence",
                        "proposed_value": "raise priority weighting",
                        "evidence": {"missed_rate": round(missed, 4), "sample": len(overrides)},
                    }
                )

        return proposals

    def _upsert_proposed(self, db: Session, proposal: dict[str, Any]) -> bool:
        # Idempotent on (suggestion_type, title) while still PROPOSED.
        existing = (
            db.query(ImprovementSuggestion)
            .filter(ImprovementSuggestion.suggestion_type == proposal["suggestion_type"])
            .filter(ImprovementSuggestion.title == proposal["title"])
            .filter(ImprovementSuggestion.status == STATUS_PROPOSED)
            .one_or_none()
        )
        if existing is not None:
            existing.rationale = proposal["rationale"]
            existing.evidence_json = proposal.get("evidence", {})
            return False
        db.add(
            ImprovementSuggestion(
                suggestion_type=proposal["suggestion_type"],
                title=proposal["title"],
                rationale=proposal["rationale"],
                current_value=proposal.get("current_value"),
                proposed_value=proposal.get("proposed_value"),
                evidence_json=proposal.get("evidence", {}),
                status=STATUS_PROPOSED,
            )
        )
        return True

    # ----------------------------------------------------- approval (gated)

    def decide(
        self,
        db: Session,
        suggestion_id: int,
        *,
        approve: bool,
        decided_by: str | None = None,
    ) -> ImprovementSuggestion | None:
        """Phase 45.12 — explicit user approval/rejection. Never auto-applies a
        production rule; only records the decision."""
        self.ensure_tables(db)
        row = (
            db.query(ImprovementSuggestion)
            .filter(ImprovementSuggestion.id == suggestion_id)
            .one_or_none()
        )
        if row is None:
            return None
        row.status = STATUS_APPROVED if approve else STATUS_REJECTED
        row.decided_at = datetime.now(timezone.utc)
        row.decided_by = decided_by
        db.commit()
        db.refresh(row)
        return row

    def list_suggestions(
        self, db: Session, *, status: str | None = None, limit: int = 200
    ) -> list[ImprovementSuggestion]:
        self.ensure_tables(db)
        q = db.query(ImprovementSuggestion)
        if status is not None:
            q = q.filter(ImprovementSuggestion.status == status.upper())
        return q.order_by(ImprovementSuggestion.created_at.desc()).limit(limit).all()


__all__ = ["ImprovementEngine", "ImprovementRunResult"]
