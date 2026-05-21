"""Phase 23, step 23.10 — Rejection memory writer.

"Memory" in the Phase 23 sense is the structured store of rejection
experience -- the ``rejected_candidates`` envelope plus its many
``rejection_reasons`` rows. This module is the only place that writes
to those tables.

The writer is **idempotent** on ``(symbol, snapshot_date)``. Re-running
the Phase 23 service on the same symbol replaces the stored reasons
rather than appending duplicates, so dashboards always show the latest
evaluation.

A future Phase 23+ may also push these rejection records into the
generic memory / vector store; that integration is left for the
memory phase. The hook here returns the written rows so a downstream
indexer can pick them up.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.common.service_utils import ensure_tables
from app.rejection.breakeven_failure_explainer import ReasonPayload
from app.rejection.rejection_categories import (
    CATEGORY_NOT_REJECTED,
    SEVERITY_NOT_REJECTED,
)
from app.rejection.rejection_classifier import RejectionClassification
from app.rejection.rejection_models import RejectedCandidate, RejectionReason


@dataclass
class WrittenRejection:
    candidate: RejectedCandidate | None
    reasons: list[RejectionReason]

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate.id if self.candidate is not None else None,
            "reason_ids": [r.id for r in self.reasons],
        }


class RejectionMemoryWriter:
    """Persists rejection candidates + reasons idempotently."""

    def write(
        self,
        db: Session,
        *,
        symbol: str,
        snapshot_date: date,
        classification: RejectionClassification,
        lifecycle_state: str,
        reason_payloads: list[ReasonPayload],
        profile_name: str | None,
        profile_version: str | None,
    ) -> WrittenRejection:
        ensure_tables(db)
        clean = (symbol or "").strip().upper()
        if not clean:
            raise ValueError("symbol is required")

        # Phase 23 invariant: when the classifier says the candidate is NOT
        # rejected (e.g. OPTION_DATA_NOT_AVAILABLE), we do not create a
        # rejected_candidates row. If a prior row existed for the same
        # (symbol, snapshot_date), leave it intact -- the row represents a
        # *historical* rejection that subsequent runs should not erase.
        if (
            classification.rejection_category == CATEGORY_NOT_REJECTED
            and classification.rejection_severity == SEVERITY_NOT_REJECTED
        ):
            return WrittenRejection(candidate=None, reasons=[])

        existing = (
            db.query(RejectedCandidate)
            .filter(RejectedCandidate.symbol == clean)
            .filter(RejectedCandidate.snapshot_date == snapshot_date)
            .one_or_none()
        )

        values = {
            "rejection_category": classification.rejection_category,
            "rejection_severity": classification.rejection_severity,
            "final_action_label": classification.final_action_label,
            "lifecycle_state": lifecycle_state,
            "is_rejected_but_interesting": bool(
                classification.is_rejected_but_interesting
            ),
            "interesting_reasons_json": list(classification.interesting_reasons),
            "summary": classification.summary,
            "profile_name": profile_name,
            "profile_version": profile_version,
        }

        if existing is None:
            candidate = RejectedCandidate(
                symbol=clean,
                snapshot_date=snapshot_date,
                **values,
            )
            db.add(candidate)
            db.flush()
        else:
            for key, value in values.items():
                setattr(existing, key, value)
            db.flush()
            candidate = existing
            # Replace stale reasons so re-runs stay idempotent.
            (
                db.query(RejectionReason)
                .filter(RejectionReason.rejected_candidate_id == candidate.id)
                .delete(synchronize_session=False)
            )
            db.flush()

        written_reasons: list[RejectionReason] = []
        for payload in reason_payloads:
            reason = RejectionReason(
                rejected_candidate_id=candidate.id,
                reason_label=payload.reason_label,
                reason_category=payload.reason_category,
                source_phase=payload.source_phase,
                explanation=payload.explanation,
                context_json=dict(payload.context),
            )
            db.add(reason)
            written_reasons.append(reason)
        db.commit()
        db.refresh(candidate)
        for reason in written_reasons:
            db.refresh(reason)
        return WrittenRejection(candidate=candidate, reasons=written_reasons)


__all__ = ["RejectionMemoryWriter", "WrittenRejection"]
