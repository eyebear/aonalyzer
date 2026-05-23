"""Phase 40, steps 40.2-40.8 — rejection & do-not-touch outcome tracker.

Reads rejected candidates (Phase 23) and active/historical freezes (Phase 24),
computes forward returns, and evaluates whether each rejection / freeze was
useful. ``would_option_have_worked`` is UNAVAILABLE unless real manual option
data existed (no fake option backfill). Idempotent per
``(symbol, snapshot_date, horizon_days, source_type)``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.common.service_utils import ensure_tables
from app.learning.forward_returns import compute_forward_return
from app.learning.rejection_outcome_models import (
    SOURCE_DO_NOT_TOUCH,
    SOURCE_REJECTION,
    WOULD_OPTION_FALSE,
    WOULD_OPTION_TRUE,
    WOULD_OPTION_UNAVAILABLE,
    RejectionOutcome,
)
from app.options.manual_option_input_service import ManualOptionInputService
from app.quant.stock_setup_models import StockSetup
from app.rejection.rejection_models import RejectedCandidate
from app.risk_control.do_not_touch_models import DoNotTouchItem

DEFAULT_HORIZON = 20
NEUTRAL_BAND_PCT = 2.0


@dataclass
class RejectionOutcomeRunResult:
    rejections_processed: int = 0
    freezes_processed: int = 0
    rows_created: int = 0
    rows_updated: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "rejections_processed": self.rejections_processed,
            "freezes_processed": self.freezes_processed,
            "rows_created": self.rows_created,
            "rows_updated": self.rows_updated,
        }


class RejectionOutcomeService:
    def __init__(
        self,
        horizon_days: int = DEFAULT_HORIZON,
        manual_option_service: ManualOptionInputService | None = None,
    ) -> None:
        self.horizon_days = horizon_days
        self.manual_option_service = manual_option_service or ManualOptionInputService()

    def ensure_tables(self, db: Session) -> None:
        ensure_tables(db)

    def run(
        self,
        db: Session,
        *,
        horizon_days: int | None = None,
        now: datetime | None = None,
    ) -> RejectionOutcomeRunResult:
        self.ensure_tables(db)
        horizon = horizon_days or self.horizon_days
        now = now or datetime.now(timezone.utc)
        result = RejectionOutcomeRunResult()

        for candidate in self._load_rejections(db):
            result.rejections_processed += 1
            created, updated = self._track_rejection(db, candidate, horizon, now)
            result.rows_created += int(created)
            result.rows_updated += int(updated)

        for freeze in self._load_freezes(db):
            result.freezes_processed += 1
            created, updated = self._track_freeze(db, freeze, horizon, now)
            result.rows_created += int(created)
            result.rows_updated += int(updated)

        db.commit()
        return result

    # ------------------------------------------------------------- loaders

    def _load_rejections(self, db: Session) -> list[RejectedCandidate]:
        try:
            return db.query(RejectedCandidate).all()
        except SQLAlchemyError:
            return []

    def _load_freezes(self, db: Session) -> list[DoNotTouchItem]:
        try:
            return db.query(DoNotTouchItem).all()
        except SQLAlchemyError:
            return []

    def _setup_for(
        self, db: Session, symbol: str, on_date: date
    ) -> StockSetup | None:
        try:
            return (
                db.query(StockSetup)
                .filter(StockSetup.symbol == symbol)
                .filter(StockSetup.snapshot_date <= on_date)
                .order_by(StockSetup.snapshot_date.desc(), StockSetup.id.desc())
                .first()
            )
        except SQLAlchemyError:
            return None

    def _option_data_existed(self, db: Session, symbol: str) -> bool:
        try:
            snaps = self.manual_option_service.list_manual_snapshots(
                db=db, symbol=symbol, limit=1
            )
        except Exception:
            return False
        return bool(snaps)

    # ----------------------------------------------------------- rejection

    def _track_rejection(
        self, db: Session, candidate: RejectedCandidate, horizon: int, now: datetime
    ) -> tuple[bool, bool]:
        setup = self._setup_for(db, candidate.symbol, candidate.snapshot_date)
        fr = compute_forward_return(
            db,
            candidate.symbol,
            candidate.snapshot_date,
            horizon,
            target_price=setup.target_price if setup else None,
            stop_price=setup.stop_price if setup else None,
            direction=(setup.direction if setup else "LONG") or "LONG",
        )
        option_existed = self._option_data_existed(db, candidate.symbol)
        would_option = self._would_option_have_worked(option_existed, fr)
        correct, too_strict, detail = self._classify_rejection(fr)

        values = {
            "category": candidate.rejection_category,
            "severity": candidate.rejection_severity,
            "direction": setup.direction if setup else None,
            "target_price": setup.target_price if setup else None,
            "stop_price": setup.stop_price if setup else None,
            "price_data_available": fr.available,
            "stock_return_pct": fr.return_pct,
            "would_stock_target_hit": fr.target_hit,
            "stop_hit": fr.stop_hit,
            "bars_used": fr.bars_used,
            "option_data_available": option_existed,
            "would_option_have_worked": would_option,
            "was_rejection_correct": correct,
            "is_too_strict": too_strict,
            "detail": detail,
            "context_json": {"forward_return": fr.to_dict()},
            "evaluated_at": now,
        }
        return self._upsert(
            db, candidate.symbol, candidate.snapshot_date, horizon, SOURCE_REJECTION, values
        )

    # ------------------------------------------------------------- freeze

    def _track_freeze(
        self, db: Session, freeze: DoNotTouchItem, horizon: int, now: datetime
    ) -> tuple[bool, bool]:
        frozen_date = (
            freeze.frozen_at.date() if freeze.frozen_at is not None else date.today()
        )
        setup = self._setup_for(db, freeze.symbol, frozen_date)
        fr = compute_forward_return(
            db,
            freeze.symbol,
            frozen_date,
            horizon,
            target_price=setup.target_price if setup else None,
            stop_price=setup.stop_price if setup else None,
            direction=(setup.direction if setup else "LONG") or "LONG",
        )
        # Freeze correctness mirrors rejection: useful if the stock did not run
        # up (avoided chasing into harm); too strict if it ran up strongly.
        correct, too_strict, detail = self._classify_rejection(fr, is_freeze=True)

        values = {
            "category": freeze.freeze_category,
            "severity": freeze.freeze_severity,
            "direction": setup.direction if setup else None,
            "target_price": setup.target_price if setup else None,
            "stop_price": setup.stop_price if setup else None,
            "price_data_available": fr.available,
            "stock_return_pct": fr.return_pct,
            "would_stock_target_hit": fr.target_hit,
            "stop_hit": fr.stop_hit,
            "bars_used": fr.bars_used,
            # Missing option data alone never created this freeze (Phase 24);
            # option outcome stays unavailable unless real option data existed.
            "option_data_available": self._option_data_existed(db, freeze.symbol),
            "would_option_have_worked": WOULD_OPTION_UNAVAILABLE,
            "was_rejection_correct": correct,
            "is_too_strict": too_strict,
            "detail": detail,
            "context_json": {"forward_return": fr.to_dict()},
            "evaluated_at": now,
        }
        return self._upsert(
            db, freeze.symbol, frozen_date, horizon, SOURCE_DO_NOT_TOUCH, values
        )

    # ----------------------------------------------------------- classify

    def _would_option_have_worked(self, option_existed: bool, fr: Any) -> str:
        if not option_existed or not fr.available:
            return WOULD_OPTION_UNAVAILABLE
        # Real option data existed: use the stock outcome as a transparent
        # proxy (a long call works when the underlying reaches its target).
        if fr.target_hit:
            return WOULD_OPTION_TRUE
        return WOULD_OPTION_FALSE

    def _classify_rejection(
        self, fr: Any, *, is_freeze: bool = False
    ) -> tuple[bool | None, bool, str]:
        if not fr.available or fr.return_pct is None:
            return None, False, "Insufficient forward price history."
        went_up = fr.return_pct >= NEUTRAL_BAND_PCT
        target_hit = bool(fr.target_hit)
        if went_up or target_hit:
            verb = "freeze" if is_freeze else "rejection"
            return False, True, f"Stock advanced — {verb} may have been too strict."
        verb = "freeze" if is_freeze else "rejection"
        return True, False, f"Stock did not advance — {verb} avoided a non-winner."

    # ------------------------------------------------------------- upsert

    def _upsert(
        self,
        db: Session,
        symbol: str,
        snapshot_date: date,
        horizon: int,
        source_type: str,
        values: dict[str, Any],
    ) -> tuple[bool, bool]:
        existing = (
            db.query(RejectionOutcome)
            .filter(RejectionOutcome.symbol == symbol)
            .filter(RejectionOutcome.snapshot_date == snapshot_date)
            .filter(RejectionOutcome.horizon_days == horizon)
            .filter(RejectionOutcome.source_type == source_type)
            .one_or_none()
        )
        if existing is None:
            db.add(
                RejectionOutcome(
                    symbol=symbol,
                    snapshot_date=snapshot_date,
                    horizon_days=horizon,
                    source_type=source_type,
                    **values,
                )
            )
            return True, False
        for key, value in values.items():
            setattr(existing, key, value)
        return False, True

    # ------------------------------------------------------------- lookups

    def list_outcomes(
        self,
        db: Session,
        *,
        symbol: str | None = None,
        source_type: str | None = None,
        limit: int = 200,
    ) -> list[RejectionOutcome]:
        self.ensure_tables(db)
        q = db.query(RejectionOutcome)
        if symbol is not None:
            q = q.filter(RejectionOutcome.symbol == symbol.strip().upper())
        if source_type is not None:
            q = q.filter(RejectionOutcome.source_type == source_type)
        return (
            q.order_by(RejectionOutcome.snapshot_date.desc(), RejectionOutcome.id.desc())
            .limit(limit)
            .all()
        )

    def pending_for_memory(
        self, db: Session, *, limit: int = 200
    ) -> list[RejectionOutcome]:
        """Phase 40.8 — outcomes ready to feed memory/learning (Phase 41)."""
        self.ensure_tables(db)
        return (
            db.query(RejectionOutcome)
            .filter(RejectionOutcome.fed_to_memory.is_(False))
            .filter(RejectionOutcome.price_data_available.is_(True))
            .order_by(RejectionOutcome.snapshot_date.desc())
            .limit(limit)
            .all()
        )


__all__ = ["RejectionOutcomeRunResult", "RejectionOutcomeService"]
