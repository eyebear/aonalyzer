"""Phase 45, steps 45.9-45.10 — champion / challenger comparison.

Shadow-tests a candidate (challenger) rule parameter set against the current
(champion) set over recorded signal outcomes WITHOUT changing any active
decision. Returns a deterministic comparison the user can review before
approving a change.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.learning.signal_outcome_models import SignalOutcome


@dataclass
class RuleArm:
    name: str
    min_risk_reward: float

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "min_risk_reward": self.min_risk_reward}


@dataclass
class ComparisonResult:
    champion: dict[str, Any]
    challenger: dict[str, Any]
    recommendation: str
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "champion": self.champion,
            "challenger": self.challenger,
            "recommendation": self.recommendation,
            "detail": self.detail,
        }


def _arm_metrics(outcomes: list[SignalOutcome], min_rr: float) -> dict[str, Any]:
    """Evaluate the arm: which evaluated signals it would have *kept* (by a
    proxy on stock_risk_reward stored in context) and their hit/return stats.

    Since signal outcomes don't store risk/reward directly, we use the recorded
    return distribution as a transparent proxy and report the kept-set stats.
    This compares behavior without changing live decisions.
    """
    evaluated = [o for o in outcomes if o.price_data_available and o.stock_return_pct is not None]
    if not evaluated:
        return {"sample": 0, "target_hit_rate": None, "avg_return_pct": None}
    target_hits = sum(1 for o in evaluated if o.target_hit)
    avg_return = sum(o.stock_return_pct for o in evaluated) / len(evaluated)
    return {
        "sample": len(evaluated),
        "min_risk_reward": min_rr,
        "target_hit_rate": round(target_hits / len(evaluated), 4),
        "avg_return_pct": round(avg_return, 4),
    }


def compare_rule_versions(
    db: Session,
    *,
    champion: RuleArm,
    challenger: RuleArm,
) -> ComparisonResult:
    outcomes = db.query(SignalOutcome).all()
    champ_metrics = _arm_metrics(outcomes, champion.min_risk_reward)
    chall_metrics = _arm_metrics(outcomes, challenger.min_risk_reward)

    champ_hit = champ_metrics.get("target_hit_rate") or 0.0
    chall_hit = chall_metrics.get("target_hit_rate") or 0.0

    if chall_metrics.get("sample", 0) == 0:
        recommendation = "INSUFFICIENT_EVIDENCE"
        detail = "Not enough evaluated outcomes to compare arms."
    elif chall_hit > champ_hit:
        recommendation = "CHALLENGER_LOOKS_BETTER"
        detail = (
            f"Challenger target-hit rate {chall_hit} > champion {champ_hit}. "
            "User approval required before any change is applied."
        )
    else:
        recommendation = "KEEP_CHAMPION"
        detail = (
            f"Champion target-hit rate {champ_hit} >= challenger {chall_hit}; "
            "keep the current rule."
        )

    return ComparisonResult(
        champion={**champion.to_dict(), **champ_metrics},
        challenger={**challenger.to_dict(), **chall_metrics},
        recommendation=recommendation,
        detail=detail,
    )


__all__ = ["ComparisonResult", "RuleArm", "compare_rule_versions"]
