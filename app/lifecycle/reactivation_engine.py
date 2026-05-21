"""Phase 25, step 25.7 — Reactivation engine.

Detects symbols whose persistent lifecycle is currently in a terminal
state (``REJECTED`` or ``INSUFFICIENT_DATA``) but whose latest Phase 22
action package now points to an **active** state. These candidates are
flagged for reactivation; the transition itself runs through the state
manager so the audit trail records ``KIND_REACTIVATION``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.common.service_utils import ensure_tables
from app.lifecycle.lifecycle_models import OpportunityLifecycle
from app.lifecycle.lifecycle_states import (
    ACTIVE_STATES,
    TERMINAL_STATES,
    normalize_phase22_state,
)


@dataclass
class ReactivationCandidate:
    symbol: str
    current_state: str
    target_state: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "current_state": self.current_state,
            "target_state": self.target_state,
        }


@dataclass
class ReactivationDetectionResult:
    candidates: list[ReactivationCandidate] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"candidates": [c.to_dict() for c in self.candidates]}


class ReactivationEngine:
    """Detects which terminal-state lifecycles should be reactivated.

    The caller (typically the lifecycle update job) maps over each
    candidate by re-running the Phase 22 evaluation; this engine is
    deliberately lightweight and never mutates anything itself.
    """

    def ensure_tables(self, db: Session) -> None:
        ensure_tables(db)

    def detect(
        self,
        db: Session,
        *,
        latest_actions: dict[str, str],
    ) -> ReactivationDetectionResult:
        """Return reactivation candidates.

        ``latest_actions`` is a ``{symbol: phase22_lifecycle_state}`` map
        (already normalized would also work). The engine only flags
        symbols whose persistent state is terminal but whose latest
        Phase 22 lifecycle has moved into an active state.
        """
        self.ensure_tables(db)
        rows = (
            db.query(OpportunityLifecycle)
            .filter(OpportunityLifecycle.current_state.in_(list(TERMINAL_STATES)))
            .all()
        )
        out: list[ReactivationCandidate] = []
        for row in rows:
            latest = latest_actions.get(row.symbol)
            if latest is None:
                continue
            target = normalize_phase22_state(latest)
            if target in ACTIVE_STATES:
                out.append(
                    ReactivationCandidate(
                        symbol=row.symbol,
                        current_state=row.current_state,
                        target_state=target,
                    )
                )
        return ReactivationDetectionResult(candidates=out)


__all__ = [
    "ReactivationCandidate",
    "ReactivationDetectionResult",
    "ReactivationEngine",
]
