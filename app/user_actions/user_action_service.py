"""Phase 38, steps 38.4-38.11 — user action service + override outcome tracking.

Records user actions (review/watch/ignore/reject/manual_trade/paste_option),
detects overrides, evaluates override outcomes deterministically from forward
returns, derives missed-opportunity / avoided-correctly flags, summarizes user
decision quality, and exposes the records that feed memory/learning (Phase 41).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.common.service_utils import ensure_tables
from app.learning.forward_returns import compute_forward_return
from app.quant.stock_setup_models import StockSetup
from app.user_actions.override_detector import detect_override
from app.user_actions.user_action_models import (
    OverrideOutcome,
    UserAction,
    UserOverride,
)
from app.user_actions.user_action_types import (
    ACTION_MANUAL_TRADE,
    ALL_ACTION_TYPES,
    OPTION_DATA_ABSENT,
    OPTION_DATA_PRESENT,
    OUTCOME_NEUTRAL,
    OUTCOME_PENDING,
    OUTCOME_SYSTEM_RIGHT,
    OUTCOME_USER_RIGHT,
    OVERRIDE_IGNORED_RECOMMENDATION,
    OVERRIDE_TRADED_AGAINST_REJECTION,
)

DEFAULT_OUTCOME_HORIZON = 20
# A move of at least this magnitude (%) is treated as a directional outcome;
# smaller moves are NEUTRAL so noise is not mistaken for a verdict.
NEUTRAL_BAND_PCT = 2.0


@dataclass
class RecordActionResult:
    action: UserAction
    override: UserOverride | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action.id,
            "override_id": self.override.id if self.override is not None else None,
            "override_type": self.override.override_type
            if self.override is not None
            else None,
        }


class UserActionService:
    def __init__(self, outcome_horizon: int = DEFAULT_OUTCOME_HORIZON) -> None:
        self.outcome_horizon = outcome_horizon

    def ensure_tables(self, db: Session) -> None:
        ensure_tables(db)

    # --------------------------------------------------------------- record

    def record_action(
        self,
        db: Session,
        *,
        symbol: str,
        action_type: str,
        system_suggestion_label: str | None = None,
        system_instrument_scope: str | None = None,
        manual_option_snapshot_id: int | None = None,
        option_data_available: bool | None = None,
        action_date: date | None = None,
        notes: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> RecordActionResult:
        self.ensure_tables(db)
        clean = (symbol or "").strip().upper()
        if not clean:
            raise ValueError("symbol is required")
        action_type = (action_type or "").strip().upper()
        if action_type not in ALL_ACTION_TYPES:
            raise ValueError(f"unknown action_type '{action_type}'")

        availability = None
        if option_data_available is not None:
            availability = OPTION_DATA_PRESENT if option_data_available else OPTION_DATA_ABSENT
        elif manual_option_snapshot_id is not None:
            availability = OPTION_DATA_PRESENT

        action = UserAction(
            symbol=clean,
            action_type=action_type,
            action_date=action_date or date.today(),
            system_suggestion_label=system_suggestion_label,
            system_instrument_scope=system_instrument_scope,
            option_data_availability=availability,
            manual_option_snapshot_id=manual_option_snapshot_id,
            notes=notes,
            context_json=context or {},
        )
        db.add(action)
        db.commit()
        db.refresh(action)

        override = None
        override_type = detect_override(
            system_suggestion_label=system_suggestion_label,
            user_action_type=action_type,
        )
        if override_type is not None:
            override = UserOverride(
                user_action_id=action.id,
                symbol=clean,
                override_type=override_type,
                system_suggestion_label=system_suggestion_label,
                user_action_type=action_type,
                signal_date=action.action_date,
                context_json=context or {},
            )
            db.add(override)
            db.commit()
            db.refresh(override)

        return RecordActionResult(action=action, override=override)

    # ------------------------------------------------------ outcome tracking

    def track_override_outcomes(
        self,
        db: Session,
        *,
        horizon_days: int | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Phase 38.6-38.8 — evaluate each override from forward returns."""
        self.ensure_tables(db)
        horizon = horizon_days or self.outcome_horizon
        now = now or datetime.now(timezone.utc)

        overrides = db.query(UserOverride).all()
        created = 0
        updated = 0
        for override in overrides:
            outcome = self._evaluate_override(db, override, horizon, now)
            if outcome[0]:
                created += 1
            elif outcome[1]:
                updated += 1
        db.commit()
        return {"overrides": len(overrides), "created": created, "updated": updated}

    def _evaluate_override(
        self, db: Session, override: UserOverride, horizon: int, now: datetime
    ) -> tuple[bool, bool]:
        setup = self._setup_for(db, override.symbol, override.signal_date)
        fr = compute_forward_return(
            db,
            override.symbol,
            override.signal_date or date.today(),
            horizon,
            target_price=setup.target_price if setup else None,
            stop_price=setup.stop_price if setup else None,
            direction=(setup.direction if setup else "LONG") or "LONG",
        )

        classification, missed, avoided, detail = self._classify(
            override.override_type, fr
        )

        values = {
            "symbol": override.symbol,
            "override_type": override.override_type,
            "outcome_classification": classification,
            "stock_return_pct": fr.return_pct,
            "target_hit": fr.target_hit,
            "stop_hit": fr.stop_hit,
            "price_data_available": fr.available,
            "is_missed_opportunity": missed,
            "is_avoided_correctly": avoided,
            "detail": detail,
            "context_json": {"forward_return": fr.to_dict()},
            "evaluated_at": now,
        }

        existing = (
            db.query(OverrideOutcome)
            .filter(OverrideOutcome.user_override_id == override.id)
            .filter(OverrideOutcome.horizon_days == horizon)
            .one_or_none()
        )
        if existing is None:
            db.add(
                OverrideOutcome(
                    user_override_id=override.id,
                    horizon_days=horizon,
                    **values,
                )
            )
            return True, False
        for key, value in values.items():
            setattr(existing, key, value)
        return False, True

    def _classify(
        self, override_type: str, fr: Any
    ) -> tuple[str, bool, bool, str]:
        if not fr.available or fr.return_pct is None:
            return OUTCOME_PENDING, False, False, "Insufficient forward price history."

        went_up = fr.return_pct >= NEUTRAL_BAND_PCT
        went_down = fr.return_pct <= -NEUTRAL_BAND_PCT
        target_hit = bool(fr.target_hit)
        stop_hit = bool(fr.stop_hit)

        if override_type == OVERRIDE_TRADED_AGAINST_REJECTION:
            # User traded despite rejection: user right if it rose / hit target.
            if went_up or target_hit:
                return OUTCOME_USER_RIGHT, False, False, "Stock rose after trade-against-rejection."
            if went_down or stop_hit:
                return OUTCOME_SYSTEM_RIGHT, False, False, "Stock fell; rejection was appropriate."
            return OUTCOME_NEUTRAL, False, False, "Move within neutral band."

        if override_type == OVERRIDE_IGNORED_RECOMMENDATION:
            # User passed on a recommendation: system right (missed) if it rose.
            if went_up or target_hit:
                return (
                    OUTCOME_SYSTEM_RIGHT,
                    True,
                    False,
                    "Ignored recommendation rose — missed opportunity.",
                )
            if went_down or stop_hit:
                return (
                    OUTCOME_USER_RIGHT,
                    False,
                    True,
                    "Ignored recommendation fell — correctly avoided.",
                )
            return OUTCOME_NEUTRAL, False, False, "Move within neutral band."

        return OUTCOME_NEUTRAL, False, False, "Unclassified override type."

    def _setup_for(
        self, db: Session, symbol: str, signal_date: date | None
    ) -> StockSetup | None:
        try:
            q = db.query(StockSetup).filter(StockSetup.symbol == symbol)
            if signal_date is not None:
                q = q.filter(StockSetup.snapshot_date <= signal_date)
            return q.order_by(
                StockSetup.snapshot_date.desc(), StockSetup.id.desc()
            ).first()
        except SQLAlchemyError:
            return None

    # ------------------------------------------------------ analysis + feed

    def analyze_decision_quality(self, db: Session) -> dict[str, Any]:
        """Phase 38.10 — summarize user behavior (deterministic counts)."""
        self.ensure_tables(db)
        actions = db.query(UserAction).all()
        overrides = db.query(UserOverride).all()
        outcomes = db.query(OverrideOutcome).all()

        manual_trades = sum(1 for a in actions if a.action_type == ACTION_MANUAL_TRADE)
        manual_option_actions = sum(
            1 for a in actions if a.manual_option_snapshot_id is not None
        )

        return {
            "total_actions": len(actions),
            "manual_trades": manual_trades,
            "manual_option_actions": manual_option_actions,
            "total_overrides": len(overrides),
            "overrides_traded_against_rejection": sum(
                1 for o in overrides if o.override_type == OVERRIDE_TRADED_AGAINST_REJECTION
            ),
            "overrides_ignored_recommendation": sum(
                1 for o in overrides if o.override_type == OVERRIDE_IGNORED_RECOMMENDATION
            ),
            "user_right": sum(
                1 for o in outcomes if o.outcome_classification == OUTCOME_USER_RIGHT
            ),
            "system_right": sum(
                1 for o in outcomes if o.outcome_classification == OUTCOME_SYSTEM_RIGHT
            ),
            "neutral": sum(
                1 for o in outcomes if o.outcome_classification == OUTCOME_NEUTRAL
            ),
            "pending": sum(
                1 for o in outcomes if o.outcome_classification == OUTCOME_PENDING
            ),
            "missed_opportunities": sum(1 for o in outcomes if o.is_missed_opportunity),
            "avoided_correctly": sum(1 for o in outcomes if o.is_avoided_correctly),
        }

    def list_actions(
        self, db: Session, *, symbol: str | None = None, limit: int = 200
    ) -> list[UserAction]:
        self.ensure_tables(db)
        q = db.query(UserAction)
        if symbol is not None:
            q = q.filter(UserAction.symbol == symbol.strip().upper())
        return q.order_by(UserAction.created_at.desc()).limit(limit).all()

    def list_overrides(
        self, db: Session, *, symbol: str | None = None, limit: int = 200
    ) -> list[UserOverride]:
        self.ensure_tables(db)
        q = db.query(UserOverride)
        if symbol is not None:
            q = q.filter(UserOverride.symbol == symbol.strip().upper())
        return q.order_by(UserOverride.detected_at.desc()).limit(limit).all()

    def pending_for_memory(self, db: Session, *, limit: int = 200) -> list[OverrideOutcome]:
        """Phase 38.11 — outcomes ready to feed memory/learning (Phase 41)."""
        self.ensure_tables(db)
        return (
            db.query(OverrideOutcome)
            .filter(OverrideOutcome.fed_to_memory.is_(False))
            .filter(OverrideOutcome.outcome_classification != OUTCOME_PENDING)
            .order_by(OverrideOutcome.created_at.desc())
            .limit(limit)
            .all()
        )


__all__ = ["RecordActionResult", "UserActionService"]
