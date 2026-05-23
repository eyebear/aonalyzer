"""Phase 27, step 27.3 — daily worklist generator.

Reads existing persisted research artifacts and assembles practical daily
tasks. It NEVER recomputes decisions or invents data — it only surfaces what
the deterministic upstream layers already produced:

* action suggestions  -> ready / watch / wait items (+ PASTE_OPTION_DATA)
* review queue         -> due reviews
* do-not-touch items   -> risk alerts
* high-importance events-> news tasks
* decision snapshots   -> experience (memory-risk) warnings

The PASTE_OPTION_DATA item is generated **only** when the stock thesis is
valid but the option expression could not be evaluated because manual option
data is unavailable / incomplete — never for a stock-blocked candidate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.action.action_models import ActionSuggestion
from app.database.models import Event
from app.decision.decision_models import DecisionSnapshot
from app.review.review_models import ReviewQueueItem
from app.review.review_trigger_types import ACTIVE_QUEUE_STATUSES
from app.risk_control.do_not_touch_models import DoNotTouchItem
from app.worklist.worklist_types import (
    PRIORITY_HIGH,
    PRIORITY_LOW,
    PRIORITY_MEDIUM,
    SOURCE_ACTION_SUGGESTION,
    SOURCE_EXPERIENCE_WARNING,
    SOURCE_IMPORTANT_EVENT,
    SOURCE_MANUAL_OPTION_PASTE,
    SOURCE_REVIEW_QUEUE,
    SOURCE_RISK_ALERT,
    WORKLIST_ACTION_READY,
    WORKLIST_ACTION_WAIT,
    WORKLIST_ACTION_WATCH,
    WORKLIST_DUE_REVIEW,
    WORKLIST_EXPERIENCE_WARNING,
    WORKLIST_IMPORTANT_EVENT,
    WORKLIST_PASTE_OPTION_DATA,
    WORKLIST_RISK_ALERT,
)

# Final action labels whose *stock* thesis is valid (option side may vary).
STOCK_VALID_LABELS = frozenset(
    {
        "READY_TO_RESEARCH_STOCK_ONLY",
        "READY_TO_RESEARCH_WITH_OPTION",
        "STOCK_OK_OPTION_BAD",
        "WATCH_STOCK_ONLY",
        "WAIT_FOR_ENTRY_STOCK_ONLY",
        "OPTION_DATA_NOT_AVAILABLE",
    }
)

# Stock-blocked labels — never eligible for PASTE_OPTION_DATA.
STOCK_BLOCKED_LABELS = frozenset({"NO_TRADE", "INSUFFICIENT_PRICE_HISTORY"})

# Labels that map to a primary action worklist type.
_READY_LABELS = frozenset(
    {"READY_TO_RESEARCH_STOCK_ONLY", "READY_TO_RESEARCH_WITH_OPTION"}
)


@dataclass
class WorklistItemDraft:
    """An un-persisted candidate worklist item produced by the generator."""

    symbol: str
    worklist_type: str
    source: str
    priority: str
    title: str
    summary: str
    context: dict[str, Any] = field(default_factory=dict)
    final_action_label: str | None = None
    lifecycle_state: str | None = None
    instrument_scope: str | None = None
    rank: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "worklist_type": self.worklist_type,
            "source": self.source,
            "priority": self.priority,
            "title": self.title,
            "summary": self.summary,
            "context": dict(self.context),
            "final_action_label": self.final_action_label,
            "lifecycle_state": self.lifecycle_state,
            "instrument_scope": self.instrument_scope,
            "rank": self.rank,
        }

    @property
    def dedupe_key(self) -> tuple[str, str, str]:
        return (self.symbol, self.source, self.worklist_type)


class WorklistGenerator:
    """Pulls drafts from the persisted research layers (read-only)."""

    def __init__(self, *, important_event_window_hours: int = 72) -> None:
        self.important_event_window_hours = important_event_window_hours

    def generate(
        self,
        db: Session,
        *,
        worklist_date: date | None = None,
        symbols: list[str] | None = None,
        now: datetime | None = None,
    ) -> list[WorklistItemDraft]:
        now = now or datetime.now(timezone.utc)
        symbol_filter = (
            {s.strip().upper() for s in symbols if s and s.strip()}
            if symbols is not None
            else None
        )

        drafts: list[WorklistItemDraft] = []
        drafts.extend(self._from_action_suggestions(db, symbol_filter))
        drafts.extend(self._from_review_queue(db, symbol_filter))
        drafts.extend(self._from_risk_alerts(db, symbol_filter))
        drafts.extend(self._from_important_events(db, symbol_filter, now))
        drafts.extend(self._from_experience_warnings(db, symbol_filter))
        return drafts

    # ------------------------------------------------------- action suggestions

    def _latest_action_per_symbol(
        self, db: Session, symbol_filter: set[str] | None
    ) -> list[ActionSuggestion]:
        try:
            q = db.query(ActionSuggestion)
            if symbol_filter is not None:
                q = q.filter(ActionSuggestion.symbol.in_(sorted(symbol_filter)))
            rows = q.order_by(
                ActionSuggestion.snapshot_date.desc(),
                ActionSuggestion.id.desc(),
            ).all()
        except SQLAlchemyError:
            return []
        latest: dict[str, ActionSuggestion] = {}
        for row in rows:
            if row.symbol not in latest:
                latest[row.symbol] = row
        return list(latest.values())

    def _from_action_suggestions(
        self, db: Session, symbol_filter: set[str] | None
    ) -> list[WorklistItemDraft]:
        drafts: list[WorklistItemDraft] = []
        for row in self._latest_action_per_symbol(db, symbol_filter):
            label = row.final_action_label or ""
            if label in STOCK_BLOCKED_LABELS:
                # Stock-blocked candidates produce no action / paste task.
                continue

            primary = self._primary_action_draft(row, label)
            if primary is not None:
                drafts.append(primary)

            paste = self._paste_option_draft(row, label)
            if paste is not None:
                drafts.append(paste)
        return drafts

    def _primary_action_draft(
        self, row: ActionSuggestion, label: str
    ) -> WorklistItemDraft | None:
        if label in _READY_LABELS:
            worklist_type = WORKLIST_ACTION_READY
            priority = PRIORITY_HIGH
        elif label == "WAIT_FOR_ENTRY_STOCK_ONLY":
            worklist_type = WORKLIST_ACTION_WAIT
            priority = PRIORITY_MEDIUM
        elif label in ("WATCH_STOCK_ONLY", "STOCK_OK_OPTION_BAD", "OPTION_DATA_NOT_AVAILABLE"):
            worklist_type = WORKLIST_ACTION_WATCH
            priority = PRIORITY_MEDIUM
        else:
            return None

        summary = row.suggested_action_summary or label
        return WorklistItemDraft(
            symbol=row.symbol,
            worklist_type=worklist_type,
            source=SOURCE_ACTION_SUGGESTION,
            priority=priority,
            title=f"{row.symbol}: {label}",
            summary=summary,
            context={
                "snapshot_date": row.snapshot_date.isoformat()
                if row.snapshot_date
                else None,
                "priority_score": row.priority_score,
                "confidence_score": row.confidence_score,
                "option_expression_status": row.option_expression_status,
            },
            final_action_label=label,
            lifecycle_state=row.lifecycle_state,
            instrument_scope=row.instrument_scope,
        )

    def _paste_option_draft(
        self, row: ActionSuggestion, label: str
    ) -> WorklistItemDraft | None:
        # Stock thesis must be valid (already filtered out blocked labels).
        if label not in STOCK_VALID_LABELS:
            return None
        # Option side must be UNAVAILABLE / NOT-EVALUATED — not a rejected
        # (but complete) contract. STOCK_OK_OPTION_BAD means option data WAS
        # available and complete; analysis proceeded, so no paste prompt.
        option_status = (row.option_expression_status or "").upper()
        option_missing = label == "OPTION_DATA_NOT_AVAILABLE" or (
            bool(row.manual_option_input_needed)
            and option_status in ("OPTION_EXPR_NOT_EVALUATED", "NOT_EVALUATED", "")
        )
        if not option_missing:
            return None
        return WorklistItemDraft(
            symbol=row.symbol,
            worklist_type=WORKLIST_PASTE_OPTION_DATA,
            source=SOURCE_MANUAL_OPTION_PASTE,
            priority=PRIORITY_HIGH
            if label == "OPTION_DATA_NOT_AVAILABLE"
            else PRIORITY_MEDIUM,
            title=f"{row.symbol}: paste option data",
            summary=(
                "Stock thesis is valid but the option expression cannot be "
                "evaluated — paste a manual option contract to enable the "
                "option-aware path. Stock-only research can still proceed."
            ),
            context={
                "snapshot_date": row.snapshot_date.isoformat()
                if row.snapshot_date
                else None,
                "option_expression_status": row.option_expression_status,
                "option_contract_criteria": row.option_contract_criteria_json,
            },
            final_action_label=label,
            lifecycle_state=row.lifecycle_state,
            instrument_scope=row.instrument_scope,
        )

    # --------------------------------------------------------------- review queue

    def _from_review_queue(
        self, db: Session, symbol_filter: set[str] | None
    ) -> list[WorklistItemDraft]:
        try:
            q = db.query(ReviewQueueItem).filter(
                ReviewQueueItem.status.in_(sorted(ACTIVE_QUEUE_STATUSES))
            )
            if symbol_filter is not None:
                q = q.filter(ReviewQueueItem.symbol.in_(sorted(symbol_filter)))
            rows = q.order_by(ReviewQueueItem.priority.asc()).all()
        except SQLAlchemyError:
            return []

        drafts: list[WorklistItemDraft] = []
        for row in rows:
            drafts.append(
                WorklistItemDraft(
                    symbol=row.symbol,
                    worklist_type=WORKLIST_DUE_REVIEW,
                    source=SOURCE_REVIEW_QUEUE,
                    priority=(row.priority or PRIORITY_MEDIUM).upper(),
                    title=f"{row.symbol}: review due ({row.trigger_type})",
                    summary=row.summary or row.review_reason_label,
                    context={
                        "queue_item_id": row.id,
                        "trigger_type": row.trigger_type,
                        "review_reason_label": row.review_reason_label,
                        "due_at": row.due_at.isoformat() if row.due_at else None,
                    },
                    lifecycle_state=row.lifecycle_state,
                )
            )
        return drafts

    # ----------------------------------------------------------------- risk alerts

    def _from_risk_alerts(
        self, db: Session, symbol_filter: set[str] | None
    ) -> list[WorklistItemDraft]:
        try:
            q = db.query(DoNotTouchItem).filter(DoNotTouchItem.is_active.is_(True))
            if symbol_filter is not None:
                q = q.filter(DoNotTouchItem.symbol.in_(sorted(symbol_filter)))
            rows = q.all()
        except SQLAlchemyError:
            return []

        drafts: list[WorklistItemDraft] = []
        for row in rows:
            severity = (row.freeze_severity or "").upper()
            priority = PRIORITY_HIGH if "HARD" in severity else PRIORITY_MEDIUM
            drafts.append(
                WorklistItemDraft(
                    symbol=row.symbol,
                    worklist_type=WORKLIST_RISK_ALERT,
                    source=SOURCE_RISK_ALERT,
                    priority=priority,
                    title=f"{row.symbol}: do-not-touch ({row.freeze_category})",
                    summary=row.reason_summary
                    or "This symbol is currently frozen.",
                    context={
                        "freeze_category": row.freeze_category,
                        "freeze_severity": row.freeze_severity,
                        "expires_at": row.expires_at.isoformat()
                        if row.expires_at
                        else None,
                        "release_condition_label": row.release_condition_label,
                    },
                )
            )
        return drafts

    # ------------------------------------------------------------- important events

    def _from_important_events(
        self,
        db: Session,
        symbol_filter: set[str] | None,
        now: datetime,
    ) -> list[WorklistItemDraft]:
        cutoff = now - timedelta(hours=self.important_event_window_hours)
        try:
            q = db.query(Event).filter(
                Event.importance_level.in_(["HIGH", "high", "High"])
            )
            if symbol_filter is not None:
                q = q.filter(Event.symbol.in_(sorted(symbol_filter)))
            rows = q.order_by(Event.event_time.desc()).limit(100).all()
        except SQLAlchemyError:
            return []

        drafts: list[WorklistItemDraft] = []
        seen: set[str] = set()
        for row in rows:
            symbol = (row.symbol or "").upper()
            if not symbol or symbol in seen:
                continue
            # Recency filter — only surface fresh events. Rows without an
            # event_time are conservatively included.
            if row.event_time is not None:
                event_time = row.event_time
                if event_time.tzinfo is None:
                    event_time = event_time.replace(tzinfo=timezone.utc)
                if event_time < cutoff:
                    continue
            seen.add(symbol)
            drafts.append(
                WorklistItemDraft(
                    symbol=symbol,
                    worklist_type=WORKLIST_IMPORTANT_EVENT,
                    source=SOURCE_IMPORTANT_EVENT,
                    priority=PRIORITY_MEDIUM,
                    title=f"{symbol}: review important event",
                    summary=(row.headline or row.source_title or "Important event")[
                        :500
                    ],
                    context={
                        "event_id": row.id,
                        "event_type": row.event_type,
                        "source_url": row.source_url,
                        "event_time": row.event_time.isoformat()
                        if row.event_time
                        else None,
                    },
                )
            )
        return drafts

    # --------------------------------------------------------- experience warnings

    def _from_experience_warnings(
        self, db: Session, symbol_filter: set[str] | None
    ) -> list[WorklistItemDraft]:
        try:
            q = db.query(DecisionSnapshot).filter(
                DecisionSnapshot.memory_risk_level.in_(["HIGH", "high", "High"])
            )
            if symbol_filter is not None:
                q = q.filter(DecisionSnapshot.symbol.in_(sorted(symbol_filter)))
            rows = q.order_by(
                DecisionSnapshot.snapshot_date.desc(), DecisionSnapshot.id.desc()
            ).all()
        except SQLAlchemyError:
            return []

        drafts: list[WorklistItemDraft] = []
        seen: set[str] = set()
        for row in rows:
            if row.symbol in seen:
                continue
            seen.add(row.symbol)
            drafts.append(
                WorklistItemDraft(
                    symbol=row.symbol,
                    worklist_type=WORKLIST_EXPERIENCE_WARNING,
                    source=SOURCE_EXPERIENCE_WARNING,
                    priority=PRIORITY_LOW,
                    title=f"{row.symbol}: experience warning",
                    summary=(
                        "Memory risk is HIGH for this symbol — similar past "
                        "cases ended unfavorably. Review before acting."
                    ),
                    context={
                        "snapshot_date": row.snapshot_date.isoformat()
                        if row.snapshot_date
                        else None,
                        "memory_risk_level": row.memory_risk_level,
                    },
                    final_action_label=row.final_label,
                )
            )
        return drafts


__all__ = ["STOCK_BLOCKED_LABELS", "STOCK_VALID_LABELS", "WorklistGenerator", "WorklistItemDraft"]
