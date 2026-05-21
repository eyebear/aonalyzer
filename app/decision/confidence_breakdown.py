"""Phase 21, step 21.9 — Confidence breakdown.

Captures the per-component contributions that feed
``confidence_score_engine``. The breakdown is intentionally a dataclass
of raw scalars so downstream phases / dashboards can render an
explanation panel without re-computing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ConfidenceBreakdown:
    components: dict[str, float] = field(default_factory=dict)
    weights: dict[str, float] = field(default_factory=dict)
    total: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "components": {k: round(v, 2) for k, v in self.components.items()},
            "weights": {k: round(v, 4) for k, v in self.weights.items()},
            "total": round(self.total, 2),
        }


def build_confidence_breakdown(
    component_scores: dict[str, float],
    weights: dict[str, float],
) -> ConfidenceBreakdown:
    """Combine per-component 0-100 scores with weights into a total.

    The weights need not sum to 1.0; if they do not, the total is rescaled
    so that a fully-passing decision lands at 100.
    """
    if not component_scores:
        return ConfidenceBreakdown(components={}, weights=dict(weights), total=0.0)

    aligned_weights = {k: float(weights.get(k, 0.0)) for k in component_scores}
    weight_sum = sum(aligned_weights.values())
    if weight_sum <= 0:
        return ConfidenceBreakdown(
            components={k: 0.0 for k in component_scores},
            weights=aligned_weights,
            total=0.0,
        )

    weighted: dict[str, float] = {}
    for k, score in component_scores.items():
        weighted[k] = float(score) * (aligned_weights[k] / weight_sum)

    total = sum(weighted.values())
    return ConfidenceBreakdown(
        components=weighted,
        weights=aligned_weights,
        total=max(0.0, min(100.0, total)),
    )


__all__ = ["ConfidenceBreakdown", "build_confidence_breakdown"]
