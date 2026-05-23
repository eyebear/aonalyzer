"""Phase 27, step 27.2 — Today's Research Worklist service.

DB-facing orchestrator: runs the generator, ranks the drafts, and upserts the
day's ``research_worklist_items`` (idempotent per
``(worklist_date, symbol, source, worklist_type)``). Re-running for the same
day refreshes existing OPEN items and removes stale auto-generated OPEN items
that no longer apply, while leaving user-resolved (DONE/DISMISSED) items
untouched for audit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.common.service_utils import ensure_tables
from app.profiles.profile_manager import profile_manager
from app.profiles.profile_models import StrategyProfile
from app.worklist.worklist_generator import WorklistGenerator, WorklistItemDraft
from app.worklist.worklist_models import ResearchWorklistItem
from app.worklist.worklist_ranker import rank_items
from app.worklist.worklist_types import (
    ACTIVE_STATUSES,
    ALL_STATUSES,
    STATUS_DISMISSED,
    STATUS_DONE,
    STATUS_OPEN,
)


@dataclass
class WorklistGenerationResult:
    worklist_date: date
    items_created: int = 0
    items_refreshed: int = 0
    items_removed: int = 0
    drafts: list[WorklistItemDraft] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "worklist_date": self.worklist_date.isoformat(),
            "items_created": self.items_created,
            "items_refreshed": self.items_refreshed,
            "items_removed": self.items_removed,
            "items_total": len(self.drafts),
            "drafts": [d.to_dict() for d in self.drafts],
        }


class TodayWorklistService:
    def __init__(self, generator: WorklistGenerator | None = None) -> None:
        self.generator = generator or WorklistGenerator()

    def ensure_tables(self, db: Session) -> None:
        ensure_tables(db)

    # --------------------------------------------------------------- generate

    def generate_worklist(
        self,
        db: Session,
        *,
        worklist_date: date | None = None,
        symbols: list[str] | None = None,
        profile: StrategyProfile | None = None,
        now: datetime | None = None,
    ) -> WorklistGenerationResult:
        self.ensure_tables(db)
        target_date = worklist_date or date.today()
        active_profile = profile or self._safe_profile()
        profile_name = active_profile.profile_name if active_profile else None
        profile_version = active_profile.profile_version if active_profile else None

        drafts = self.generator.generate(
            db, worklist_date=target_date, symbols=symbols, now=now
        )
        ranked = rank_items(drafts)

        result = WorklistGenerationResult(worklist_date=target_date, drafts=ranked)

        # Existing auto-generated items for the day, keyed by dedupe tuple.
        existing_rows = (
            db.query(ResearchWorklistItem)
            .filter(ResearchWorklistItem.worklist_date == target_date)
            .all()
        )
        existing_by_key: dict[tuple[str, str, str], ResearchWorklistItem] = {
            (row.symbol, row.source, row.worklist_type): row for row in existing_rows
        }
        seen_keys: set[tuple[str, str, str]] = set()

        for draft in ranked:
            key = draft.dedupe_key
            seen_keys.add(key)
            row = existing_by_key.get(key)
            values = {
                "priority": draft.priority,
                "rank": draft.rank,
                "title": draft.title,
                "summary": draft.summary,
                "context_json": dict(draft.context),
                "final_action_label": draft.final_action_label,
                "lifecycle_state": draft.lifecycle_state,
                "instrument_scope": draft.instrument_scope,
                "profile_name": profile_name,
                "profile_version": profile_version,
            }
            if row is None:
                db.add(
                    ResearchWorklistItem(
                        worklist_date=target_date,
                        symbol=draft.symbol,
                        worklist_type=draft.worklist_type,
                        source=draft.source,
                        status=STATUS_OPEN,
                        **values,
                    )
                )
                result.items_created += 1
            else:
                # Never resurrect a user-resolved item; only refresh OPEN ones.
                if row.status in ACTIVE_STATUSES:
                    for field_name, value in values.items():
                        setattr(row, field_name, value)
                    result.items_refreshed += 1

        # Remove stale auto-generated OPEN items no longer produced today.
        for key, row in existing_by_key.items():
            if key not in seen_keys and row.status in ACTIVE_STATUSES:
                db.delete(row)
                result.items_removed += 1

        db.commit()
        return result

    # ----------------------------------------------------------------- lookups

    def list_items(
        self,
        db: Session,
        *,
        worklist_date: date | None = None,
        status: str | None = None,
        worklist_type: str | None = None,
        symbol: str | None = None,
        limit: int = 500,
    ) -> list[ResearchWorklistItem]:
        self.ensure_tables(db)
        q = db.query(ResearchWorklistItem)
        if worklist_date is not None:
            q = q.filter(ResearchWorklistItem.worklist_date == worklist_date)
        if status is not None:
            q = q.filter(ResearchWorklistItem.status == status.upper())
        if worklist_type is not None:
            q = q.filter(ResearchWorklistItem.worklist_type == worklist_type.upper())
        if symbol is not None:
            q = q.filter(ResearchWorklistItem.symbol == symbol.strip().upper())
        return (
            q.order_by(
                ResearchWorklistItem.worklist_date.desc(),
                ResearchWorklistItem.rank.asc(),
                ResearchWorklistItem.id.asc(),
            )
            .limit(limit)
            .all()
        )

    def get_by_id(self, db: Session, item_id: int) -> ResearchWorklistItem | None:
        self.ensure_tables(db)
        return (
            db.query(ResearchWorklistItem)
            .filter(ResearchWorklistItem.id == item_id)
            .one_or_none()
        )

    # ------------------------------------------------------------------ mutate

    def transition_status(
        self,
        db: Session,
        item_id: int,
        *,
        new_status: str,
        notes: str | None = None,
    ) -> ResearchWorklistItem | None:
        self.ensure_tables(db)
        if new_status.upper() not in ALL_STATUSES:
            raise ValueError(f"unknown worklist status '{new_status}'")
        row = self.get_by_id(db, item_id)
        if row is None:
            return None
        row.status = new_status.upper()
        if row.status in (STATUS_DONE, STATUS_DISMISSED):
            row.resolved_at = datetime.now(timezone.utc)
            row.resolution_notes = notes
        elif row.status == STATUS_OPEN:
            row.resolved_at = None
            row.resolution_notes = None
        db.commit()
        db.refresh(row)
        return row

    # ------------------------------------------------------------------ helpers

    def _safe_profile(self) -> StrategyProfile | None:
        try:
            return profile_manager.get_active_profile()
        except Exception:
            return None


__all__ = ["TodayWorklistService", "WorklistGenerationResult"]
