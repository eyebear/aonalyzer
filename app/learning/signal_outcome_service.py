"""Phase 39, steps 39.2-39.12 — signal outcome tracker.

Reads persisted signals (action suggestions), pulls the stock setup's
target/stop/direction, and computes forward returns at the 5/10/20/30-day
horizons via the shared deterministic forward-return helper. Idempotent per
``(symbol, signal_date, horizon_days)``. The after-close ``run`` job is safe to
run repeatedly. Option outcome is recorded as unavailable unless real manual
option data existed; it is never fabricated.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.action.action_models import ActionSuggestion
from app.common.service_utils import ensure_tables
from app.learning.forward_returns import compute_forward_return
from app.learning.signal_outcome_models import (
    OPTION_OUTCOME_ESTIMATED,
    OPTION_OUTCOME_UNAVAILABLE,
    SignalOutcome,
)
from app.options.manual_option_input_service import ManualOptionInputService
from app.quant.stock_setup_models import StockSetup

DEFAULT_HORIZONS = (5, 10, 20, 30)


@dataclass
class OutcomeRunResult:
    signals_processed: int = 0
    rows_created: int = 0
    rows_updated: int = 0
    rows_unavailable: int = 0
    horizons: tuple[int, ...] = DEFAULT_HORIZONS

    def to_dict(self) -> dict[str, Any]:
        return {
            "signals_processed": self.signals_processed,
            "rows_created": self.rows_created,
            "rows_updated": self.rows_updated,
            "rows_unavailable": self.rows_unavailable,
            "horizons": list(self.horizons),
        }


@dataclass
class _SignalContext:
    symbol: str
    signal_date: date
    final_action_label: str | None
    instrument_scope: str | None
    direction: str | None
    entry_reference_price: float | None
    target_price: float | None
    stop_price: float | None
    manual_option_snapshot: Any | None = field(default=None)


class SignalOutcomeService:
    def __init__(
        self,
        horizons: tuple[int, ...] = DEFAULT_HORIZONS,
        manual_option_service: ManualOptionInputService | None = None,
    ) -> None:
        self.horizons = horizons
        self.manual_option_service = manual_option_service or ManualOptionInputService()

    def ensure_tables(self, db: Session) -> None:
        ensure_tables(db)

    # ------------------------------------------------------------------ run

    def run(
        self,
        db: Session,
        *,
        symbols: list[str] | None = None,
        now: datetime | None = None,
    ) -> OutcomeRunResult:
        self.ensure_tables(db)
        now = now or datetime.now(timezone.utc)
        result = OutcomeRunResult(horizons=self.horizons)

        signals = self._load_signals(db, symbols)
        for signal in signals:
            result.signals_processed += 1
            ctx = self._build_context(db, signal)
            for horizon in self.horizons:
                created, updated, unavailable = self._track_one(db, ctx, horizon, now)
                result.rows_created += int(created)
                result.rows_updated += int(updated)
                result.rows_unavailable += int(unavailable)
        db.commit()
        return result

    # ------------------------------------------------------------- signal load

    def _load_signals(
        self, db: Session, symbols: list[str] | None
    ) -> list[ActionSuggestion]:
        try:
            q = db.query(ActionSuggestion)
            if symbols is not None:
                q = q.filter(
                    ActionSuggestion.symbol.in_([s.strip().upper() for s in symbols])
                )
            return q.all()
        except SQLAlchemyError:
            return []

    def _build_context(self, db: Session, signal: ActionSuggestion) -> _SignalContext:
        setup = self._setup_for(db, signal.symbol, signal.snapshot_date)
        manual = self._latest_manual_snapshot(db, signal.symbol)
        return _SignalContext(
            symbol=signal.symbol,
            signal_date=signal.snapshot_date,
            final_action_label=signal.final_action_label,
            instrument_scope=signal.instrument_scope,
            direction=setup.direction if setup else None,
            entry_reference_price=setup.current_close if setup else None,
            target_price=setup.target_price if setup else None,
            stop_price=setup.stop_price if setup else None,
            manual_option_snapshot=manual,
        )

    def _setup_for(
        self, db: Session, symbol: str, signal_date: date
    ) -> StockSetup | None:
        try:
            return (
                db.query(StockSetup)
                .filter(StockSetup.symbol == symbol)
                .filter(StockSetup.snapshot_date <= signal_date)
                .order_by(StockSetup.snapshot_date.desc(), StockSetup.id.desc())
                .first()
            )
        except SQLAlchemyError:
            return None

    def _latest_manual_snapshot(self, db: Session, symbol: str) -> Any | None:
        try:
            snaps = self.manual_option_service.list_manual_snapshots(
                db=db, symbol=symbol, limit=1
            )
        except Exception:
            return None
        return snaps[0] if snaps else None

    # ------------------------------------------------------------- track one

    def _track_one(
        self, db: Session, ctx: _SignalContext, horizon: int, now: datetime
    ) -> tuple[bool, bool, bool]:
        fr = compute_forward_return(
            db,
            ctx.symbol,
            ctx.signal_date,
            horizon,
            target_price=ctx.target_price,
            stop_price=ctx.stop_price,
            direction=ctx.direction or "LONG",
        )

        option_status, option_return = self._option_outcome(ctx, fr.return_pct)

        values = {
            "final_action_label": ctx.final_action_label,
            "instrument_scope": ctx.instrument_scope,
            "direction": ctx.direction,
            "entry_reference_price": ctx.entry_reference_price,
            "target_price": ctx.target_price,
            "stop_price": ctx.stop_price,
            "price_data_available": fr.available,
            "stock_return_pct": fr.return_pct,
            "target_hit": fr.target_hit,
            "stop_hit": fr.stop_hit,
            "bars_used": fr.bars_used,
            "option_outcome_status": option_status,
            "option_return_pct": option_return,
            "manual_option_snapshot_id": getattr(
                ctx.manual_option_snapshot, "id", None
            ),
            "context_json": {"forward_return": fr.to_dict()},
            "evaluated_at": now,
        }

        existing = (
            db.query(SignalOutcome)
            .filter(SignalOutcome.symbol == ctx.symbol)
            .filter(SignalOutcome.signal_date == ctx.signal_date)
            .filter(SignalOutcome.horizon_days == horizon)
            .one_or_none()
        )
        if existing is None:
            row = SignalOutcome(
                symbol=ctx.symbol,
                signal_date=ctx.signal_date,
                horizon_days=horizon,
                **values,
            )
            db.add(row)
            return True, False, (not fr.available)
        for key, value in values.items():
            setattr(existing, key, value)
        return False, True, (not fr.available)

    def _option_outcome(
        self, ctx: _SignalContext, stock_return_pct: float | None
    ) -> tuple[str, float | None]:
        """Estimate the option return only when real manual option data exists.

        Otherwise the status is UNAVAILABLE (never zero, never failed). The
        estimate uses the pasted delta / premium / underlying — no values are
        invented; if any are missing the status stays UNAVAILABLE.
        """
        snap = ctx.manual_option_snapshot
        if snap is None or stock_return_pct is None:
            return OPTION_OUTCOME_UNAVAILABLE, None
        delta = getattr(snap, "delta", None)
        premium = getattr(snap, "last_price", None) or getattr(snap, "mid_price", None)
        underlying = getattr(snap, "underlying_price", None)
        if delta is None or premium in (None, 0) or underlying in (None, 0):
            return OPTION_OUTCOME_UNAVAILABLE, None
        # Underlying $ move implied by the stock return, scaled by delta into
        # option $ move, expressed as % of premium. A transparent estimate.
        underlying_move = underlying * (stock_return_pct / 100.0)
        option_dollar_move = delta * underlying_move
        option_return_pct = round(option_dollar_move / premium * 100.0, 4)
        return OPTION_OUTCOME_ESTIMATED, option_return_pct

    # ------------------------------------------------------------- lookups/feed

    def list_outcomes(
        self, db: Session, *, symbol: str | None = None, limit: int = 200
    ) -> list[SignalOutcome]:
        self.ensure_tables(db)
        q = db.query(SignalOutcome)
        if symbol is not None:
            q = q.filter(SignalOutcome.symbol == symbol.strip().upper())
        return (
            q.order_by(SignalOutcome.signal_date.desc(), SignalOutcome.horizon_days.asc())
            .limit(limit)
            .all()
        )

    def pending_for_memory(self, db: Session, *, limit: int = 200) -> list[SignalOutcome]:
        """Phase 39.11 — outcomes ready to convert into case memory (Phase 41)."""
        self.ensure_tables(db)
        return (
            db.query(SignalOutcome)
            .filter(SignalOutcome.fed_to_memory.is_(False))
            .filter(SignalOutcome.price_data_available.is_(True))
            .order_by(SignalOutcome.signal_date.desc())
            .limit(limit)
            .all()
        )

    def mark_fed_to_memory(self, db: Session, outcome_ids: list[int]) -> int:
        if not outcome_ids:
            return 0
        rows = (
            db.query(SignalOutcome)
            .filter(SignalOutcome.id.in_(outcome_ids))
            .all()
        )
        for row in rows:
            row.fed_to_memory = True
        db.commit()
        return len(rows)


__all__ = ["DEFAULT_HORIZONS", "OutcomeRunResult", "SignalOutcomeService"]
