"""Phase 26, step 26.3 — Next Review Trigger engine.

The engine wires the six evaluators (steps 26.4 - 26.9) to the
persistent ``ReviewTrigger`` rows. It does three things:

1. ``arm_for_symbol`` — given the current lifecycle / do-not-touch /
   Phase 19 context, decide which triggers should be armed for the
   symbol and upsert them into ``review_triggers``. Disarms triggers
   that are no longer relevant.
2. ``evaluate_armed`` — iterate over every armed trigger, build the
   evaluator inputs from the database, call the evaluator, and (when
   it fires) enqueue a review queue item via the queue generator.
3. ``snapshot_armed`` — lookup helper for the routes / dashboard.

The engine never re-runs upstream Phase 19/20/21/22 logic; it consumes
the persisted rows only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.common.service_utils import ensure_tables
from app.database.models import DailyPrice, Event
from app.earnings.earnings_models import EarningsRiskSnapshot
from app.iv_history.iv_models import IvRiskSnapshot
from app.lifecycle.lifecycle_models import OpportunityLifecycle
from app.lifecycle.lifecycle_states import (
    STATE_INSUFFICIENT_DATA,
    STATE_WAIT_FOR_MANUAL_OPTION_INPUT,
    STATE_WAITING_FOR_ENTRY,
)
from app.quant.stock_setup_models import StockSetup
from app.review.evaluators import (
    EvaluatorInputs,
    EvaluatorResult,
    evaluate_data_refresh_restored,
    evaluate_earnings_aftermath,
    evaluate_iv_cooled_down,
    evaluate_manual_option_input,
    evaluate_new_important_event,
    evaluate_price_entered_zone,
)
from app.review.review_models import ReviewTrigger
from app.review.review_queue_generator import (
    GeneratedQueueItem,
    ReviewQueueGenerator,
)
from app.review.review_trigger_types import (
    ALL_TRIGGER_TYPES,
    TRIGGER_DATA_REFRESH_RESTORED,
    TRIGGER_EARNINGS_AFTERMATH,
    TRIGGER_IV_COOLED_DOWN,
    TRIGGER_NEW_IMPORTANT_EVENT,
    TRIGGER_PRICE_ENTERED_ZONE,
    TRIGGER_RECHECK_AFTER_MANUAL_OPTION_INPUT,
)
from app.risk_control.do_not_touch_categories import (
    FREEZE_CATEGORY_EARNINGS_BEFORE_EXPIRATION,
    FREEZE_CATEGORY_EXTREME_OPTION_VOLATILITY,
)
from app.risk_control.do_not_touch_models import DoNotTouchItem

# The trigger type a given lifecycle state implies. ``NEW_IMPORTANT_EVENT``
# is always armed when an active lifecycle exists (it's interesting in any
# state).
_LIFECYCLE_DRIVEN_TRIGGERS: dict[str, set[str]] = {
    STATE_WAITING_FOR_ENTRY: {TRIGGER_PRICE_ENTERED_ZONE},
    STATE_WAIT_FOR_MANUAL_OPTION_INPUT: {TRIGGER_RECHECK_AFTER_MANUAL_OPTION_INPUT},
    STATE_INSUFFICIENT_DATA: {TRIGGER_DATA_REFRESH_RESTORED},
}

# Defaults (in percent points) for the IV cool-down threshold. Profiles can
# override later; for Phase 26 we use the profile reject threshold minus 10
# so a cool-down is a meaningful drop, not just sub-reject volatility.
_IV_COOLDOWN_DEFAULT_GAP_PCT = 10.0


@dataclass
class ArmingResult:
    armed: list[ReviewTrigger] = field(default_factory=list)
    disarmed: list[ReviewTrigger] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "armed": [
                {"id": t.id, "trigger_type": t.trigger_type, "symbol": t.symbol}
                for t in self.armed
            ],
            "disarmed": [
                {"id": t.id, "trigger_type": t.trigger_type, "symbol": t.symbol}
                for t in self.disarmed
            ],
        }


@dataclass
class FiredTrigger:
    symbol: str
    trigger: ReviewTrigger
    result: EvaluatorResult
    queue_item: GeneratedQueueItem

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "trigger_id": self.trigger.id,
            "trigger_type": self.trigger.trigger_type,
            "result": self.result.to_dict(),
            "queue_item": self.queue_item.to_dict(),
        }


class NextReviewTriggerEngine:
    def __init__(
        self,
        queue_generator: ReviewQueueGenerator | None = None,
    ) -> None:
        self.queue_generator = queue_generator or ReviewQueueGenerator()

    def ensure_tables(self, db: Session) -> None:
        ensure_tables(db)

    # ------------------------------------------------------------- arm

    def arm_for_symbol(
        self,
        db: Session,
        symbol: str,
        *,
        now: datetime | None = None,
    ) -> ArmingResult:
        self.ensure_tables(db)
        clean = (symbol or "").strip().upper()
        if not clean:
            raise ValueError("symbol is required")
        now = now or datetime.now(timezone.utc)

        lifecycle = (
            db.query(OpportunityLifecycle)
            .filter(OpportunityLifecycle.symbol == clean)
            .one_or_none()
        )
        desired = self._desired_triggers(db=db, symbol=clean, lifecycle=lifecycle)

        existing_rows = (
            db.query(ReviewTrigger)
            .filter(ReviewTrigger.symbol == clean)
            .all()
        )
        by_type: dict[str, ReviewTrigger] = {
            t.trigger_type: t for t in existing_rows
        }

        result = ArmingResult()

        # Arm / refresh desired triggers.
        for trigger_type in sorted(desired):
            row = by_type.get(trigger_type)
            if row is None:
                row = ReviewTrigger(
                    symbol=clean,
                    trigger_type=trigger_type,
                    is_active=True,
                    condition_json={},
                    lifecycle_state=lifecycle.current_state if lifecycle else None,
                    last_evaluated_at=now,
                    fire_count=0,
                    profile_name=lifecycle.profile_name if lifecycle else None,
                    profile_version=lifecycle.profile_version if lifecycle else None,
                )
                db.add(row)
                db.flush()
                result.armed.append(row)
            else:
                if not row.is_active:
                    row.is_active = True
                    result.armed.append(row)
                row.lifecycle_state = (
                    lifecycle.current_state if lifecycle else row.lifecycle_state
                )

        # Disarm triggers that are no longer desired.
        for trigger_type, row in by_type.items():
            if trigger_type not in desired and row.is_active:
                row.is_active = False
                result.disarmed.append(row)

        db.commit()
        for row in result.armed + result.disarmed:
            db.refresh(row)
        return result

    def _desired_triggers(
        self,
        *,
        db: Session,
        symbol: str,
        lifecycle: OpportunityLifecycle | None,
    ) -> set[str]:
        desired: set[str] = set()

        # Lifecycle-driven triggers.
        if lifecycle is not None:
            desired.update(
                _LIFECYCLE_DRIVEN_TRIGGERS.get(lifecycle.current_state, set())
            )

        # Always-on triggers for any tracked symbol.
        if lifecycle is not None:
            desired.add(TRIGGER_NEW_IMPORTANT_EVENT)

        # Earnings-aftermath when an upcoming earnings event is recorded.
        try:
            earnings = (
                db.query(EarningsRiskSnapshot)
                .filter(EarningsRiskSnapshot.symbol == symbol)
                .order_by(
                    EarningsRiskSnapshot.snapshot_date.desc(),
                    EarningsRiskSnapshot.id.desc(),
                )
                .first()
            )
        except SQLAlchemyError:
            earnings = None
        if earnings is not None and earnings.next_earnings_datetime_utc is not None:
            desired.add(TRIGGER_EARNINGS_AFTERMATH)

        # IV cool-down when a Do-Not-Touch freeze is in EXTREME_OPTION_VOLATILITY.
        try:
            freeze = (
                db.query(DoNotTouchItem)
                .filter(DoNotTouchItem.symbol == symbol)
                .filter(
                    DoNotTouchItem.freeze_category
                    == FREEZE_CATEGORY_EXTREME_OPTION_VOLATILITY
                )
                .first()
            )
        except SQLAlchemyError:
            freeze = None
        if freeze is not None:
            desired.add(TRIGGER_IV_COOLED_DOWN)

        # Earnings-aftermath also implied by an EARNINGS_BEFORE_EXPIRATION freeze.
        try:
            earnings_freeze = (
                db.query(DoNotTouchItem)
                .filter(DoNotTouchItem.symbol == symbol)
                .filter(
                    DoNotTouchItem.freeze_category
                    == FREEZE_CATEGORY_EARNINGS_BEFORE_EXPIRATION
                )
                .first()
            )
        except SQLAlchemyError:
            earnings_freeze = None
        if earnings_freeze is not None:
            desired.add(TRIGGER_EARNINGS_AFTERMATH)

        return desired & set(ALL_TRIGGER_TYPES)

    # ------------------------------------------------------------- evaluate

    def evaluate_armed(
        self,
        db: Session,
        *,
        symbols: list[str] | None = None,
        now: datetime | None = None,
    ) -> list[FiredTrigger]:
        self.ensure_tables(db)
        now = now or datetime.now(timezone.utc)

        query = db.query(ReviewTrigger).filter(ReviewTrigger.is_active.is_(True))
        if symbols is not None:
            wanted = [s.strip().upper() for s in symbols if s and s.strip()]
            query = query.filter(ReviewTrigger.symbol.in_(wanted))
        triggers = query.all()

        fired: list[FiredTrigger] = []
        for trigger in triggers:
            inputs = self._build_inputs(
                db=db, symbol=trigger.symbol, trigger=trigger
            )
            result = self._evaluate_one(trigger.trigger_type, inputs, now=now)
            trigger.last_evaluated_at = now
            if result is None:
                continue
            trigger.last_fired_at = now
            trigger.fire_count = int(trigger.fire_count or 0) + 1
            db.commit()
            db.refresh(trigger)
            queue_item = self.queue_generator.enqueue(
                db=db,
                symbol=trigger.symbol,
                evaluator_result=result,
                lifecycle_state=trigger.lifecycle_state,
                profile_name=trigger.profile_name,
                profile_version=trigger.profile_version,
                now=now,
            )
            fired.append(
                FiredTrigger(
                    symbol=trigger.symbol,
                    trigger=trigger,
                    result=result,
                    queue_item=queue_item,
                )
            )
        if not fired:
            db.commit()
        return fired

    def _evaluate_one(
        self,
        trigger_type: str,
        inputs: EvaluatorInputs,
        *,
        now: datetime,
    ) -> EvaluatorResult | None:
        if trigger_type == TRIGGER_PRICE_ENTERED_ZONE:
            return evaluate_price_entered_zone(inputs)
        if trigger_type == TRIGGER_RECHECK_AFTER_MANUAL_OPTION_INPUT:
            return evaluate_manual_option_input(inputs)
        if trigger_type == TRIGGER_IV_COOLED_DOWN:
            return evaluate_iv_cooled_down(inputs)
        if trigger_type == TRIGGER_EARNINGS_AFTERMATH:
            return evaluate_earnings_aftermath(inputs, now=now)
        if trigger_type == TRIGGER_NEW_IMPORTANT_EVENT:
            return evaluate_new_important_event(inputs)
        if trigger_type == TRIGGER_DATA_REFRESH_RESTORED:
            return evaluate_data_refresh_restored(inputs)
        return None

    @staticmethod
    def _as_utc(value: datetime | None) -> datetime | None:
        """Normalise a possibly-naive datetime to UTC-aware.

        SQLite strips tz info from ``DateTime(timezone=True)`` columns on
        read; the evaluators compare against ``datetime.now(timezone.utc)``
        so any naive value reaching them raises ``TypeError``. Assume any
        naive datetime is already in UTC (matches how the project writes
        timestamps everywhere -- ``utc_now()``).
        """
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

    def _build_inputs(
        self,
        *,
        db: Session,
        symbol: str,
        trigger: ReviewTrigger,
    ) -> EvaluatorInputs:
        lifecycle_state: str | None = trigger.lifecycle_state

        # --- Stock setup -----------------------------------------------
        setup = (
            db.query(StockSetup)
            .filter(StockSetup.symbol == symbol)
            .order_by(StockSetup.snapshot_date.desc(), StockSetup.id.desc())
            .first()
        )
        current_close = setup.current_close if setup else None
        entry_low = setup.entry_zone_low if setup else None
        entry_high = setup.entry_zone_high if setup else None

        # --- Manual option snapshot (raw SQL via service uses Phase 8 table).
        # The engine only needs a binary "is there a snapshot newer than the
        # armed_at timestamp?" The Phase 8 service stores snapshots in
        # ``manual_option_snapshots`` via raw SQL; we read the table only if
        # it exists.
        has_manual = False
        manual_at: datetime | None = None
        try:
            from sqlalchemy import inspect as sa_inspect

            insp = sa_inspect(db.get_bind())
            if "manual_option_snapshots" in insp.get_table_names():
                from sqlalchemy import text

                row = (
                    db.execute(
                        text(
                            "SELECT created_at FROM manual_option_snapshots "
                            "WHERE symbol = :symbol "
                            "ORDER BY id DESC LIMIT 1"
                        ),
                        {"symbol": symbol},
                    )
                    .mappings()
                    .first()
                )
                if row is not None and row.get("created_at") is not None:
                    raw = row["created_at"]
                    if isinstance(raw, datetime):
                        manual_at = raw
                    else:
                        try:
                            manual_at = datetime.fromisoformat(str(raw))
                        except ValueError:
                            manual_at = None
                    manual_at = self._as_utc(manual_at)
                    has_manual = manual_at is not None
        except Exception:
            has_manual = False
            manual_at = None

        # --- IV ---------------------------------------------------------
        latest_iv_pct: float | None = None
        iv_threshold: float | None = None
        try:
            iv_row = (
                db.query(IvRiskSnapshot)
                .filter(IvRiskSnapshot.symbol == symbol)
                .order_by(
                    IvRiskSnapshot.snapshot_date.desc(),
                    IvRiskSnapshot.id.desc(),
                )
                .first()
            )
        except SQLAlchemyError:
            iv_row = None
        if iv_row is not None:
            latest_iv_pct = iv_row.current_iv
            if iv_row.iv_reject_threshold is not None:
                iv_threshold = max(
                    0.0,
                    float(iv_row.iv_reject_threshold) - _IV_COOLDOWN_DEFAULT_GAP_PCT,
                )

        # --- Earnings ---------------------------------------------------
        next_earnings_dt: datetime | None = None
        last_earnings_dt: datetime | None = None
        try:
            earnings = (
                db.query(EarningsRiskSnapshot)
                .filter(EarningsRiskSnapshot.symbol == symbol)
                .order_by(
                    EarningsRiskSnapshot.snapshot_date.desc(),
                    EarningsRiskSnapshot.id.desc(),
                )
                .first()
            )
        except SQLAlchemyError:
            earnings = None
        if earnings is not None and earnings.next_earnings_datetime_utc is not None:
            next_earnings_dt = earnings.next_earnings_datetime_utc
            last_earnings_dt = earnings.next_earnings_datetime_utc

        # --- News -------------------------------------------------------
        high_count = 0
        last_high_at: datetime | None = None
        try:
            cutoff = trigger.last_evaluated_at
            q = (
                db.query(Event)
                .filter(Event.symbol == symbol)
                .filter(Event.importance_level.in_(["HIGH", "high", "High"]))
            )
            if cutoff is not None:
                q = q.filter(Event.detected_time > cutoff)
            high_count = q.count()
            latest_event = q.order_by(Event.detected_time.desc()).first()
            if latest_event is not None:
                last_high_at = latest_event.detected_time
        except SQLAlchemyError:
            high_count = 0

        # --- Data refresh ----------------------------------------------
        previously_insufficient = (
            lifecycle_state == STATE_INSUFFICIENT_DATA
        )
        now_sufficient = False
        insufficient_labels: list[str] = []
        if previously_insufficient and setup is not None:
            # If the stock-setup row now reports SUFFICIENT or PARTIAL, the
            # underlying data has been restored.
            if (setup.data_sufficiency_status or "").upper() in {
                "SUFFICIENT",
                "PARTIAL",
            }:
                now_sufficient = True
            insufficient_labels = list(setup.insufficient_reasons_json or [])
        else:
            # Look at the price row count as a fallback heuristic so the
            # evaluator can also fire after a fresh market-data refresh
            # without a stored setup snapshot.
            try:
                price_count = (
                    db.query(DailyPrice)
                    .filter(DailyPrice.symbol == symbol)
                    .count()
                )
            except SQLAlchemyError:
                price_count = 0
            previously_insufficient = previously_insufficient or (
                lifecycle_state == STATE_INSUFFICIENT_DATA
            )
            now_sufficient = price_count >= 50 and previously_insufficient

        return EvaluatorInputs(
            symbol=symbol,
            lifecycle_state=lifecycle_state,
            current_close=current_close,
            entry_zone_low=entry_low,
            entry_zone_high=entry_high,
            has_manual_option_snapshot=has_manual,
            manual_option_snapshot_created_at=self._as_utc(manual_at),
            trigger_armed_at=self._as_utc(trigger.created_at),
            latest_iv_percent=latest_iv_pct,
            iv_cool_threshold_percent=iv_threshold,
            next_earnings_datetime_utc=self._as_utc(next_earnings_dt),
            last_earnings_datetime_utc=self._as_utc(last_earnings_dt),
            high_importance_event_count_since_last_eval=high_count,
            last_high_importance_event_at=self._as_utc(last_high_at),
            previously_insufficient=previously_insufficient,
            now_sufficient=now_sufficient,
            insufficient_labels=insufficient_labels,
        )

    # ------------------------------------------------------------- helpers

    def list_armed(
        self,
        db: Session,
        *,
        symbol: str | None = None,
    ) -> list[ReviewTrigger]:
        self.ensure_tables(db)
        q = db.query(ReviewTrigger).filter(ReviewTrigger.is_active.is_(True))
        if symbol is not None:
            q = q.filter(ReviewTrigger.symbol == symbol.strip().upper())
        return q.order_by(ReviewTrigger.id.asc()).all()


__all__ = [
    "ArmingResult",
    "FiredTrigger",
    "NextReviewTriggerEngine",
]
