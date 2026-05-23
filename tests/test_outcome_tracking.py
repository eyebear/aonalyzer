"""Phases 38-40 — user actions, signal outcomes, rejection/DNT outcomes.

Protects: override classification, deterministic outcomes from forward returns,
insufficient-price-history handling, target/stop detection, duplicate
prevention, and the invariant that option outcomes are never fabricated when no
manual option data existed.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.action.action_models import ActionSuggestion
from app.database.base import Base
from app.database.models import DailyPrice
from app.learning.forward_returns import compute_forward_return
from app.learning.rejection_outcome_models import (
    SOURCE_REJECTION,
    WOULD_OPTION_UNAVAILABLE,
    RejectionOutcome,
)
from app.learning.rejection_outcome_service import RejectionOutcomeService
from app.learning.signal_outcome_models import (
    OPTION_OUTCOME_UNAVAILABLE,
    SignalOutcome,
)
from app.learning.signal_outcome_service import SignalOutcomeService
from app.quant.stock_setup_models import StockSetup
from app.rejection.rejection_models import RejectedCandidate
from app.user_actions.override_detector import detect_override
from app.user_actions.user_action_models import OverrideOutcome, UserOverride
from app.user_actions.user_action_service import UserActionService
from app.user_actions.user_action_types import (
    OUTCOME_SYSTEM_RIGHT,
    OUTCOME_USER_RIGHT,
    OVERRIDE_IGNORED_RECOMMENDATION,
    OVERRIDE_TRADED_AGAINST_REJECTION,
)

_engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
)
_TestSession = sessionmaker(bind=_engine, autoflush=False, autocommit=False)
SIGNAL_DATE = date(2026, 3, 2)


@pytest.fixture(autouse=True)
def reset_db():
    Base.metadata.drop_all(bind=_engine)
    with _engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS manual_option_snapshots"))
    Base.metadata.create_all(bind=_engine)
    yield


def _seed_prices(symbol: str, n: int, *, start_close: float = 100.0, step: float = 1.0) -> None:
    """Seed n daily bars rising by ``step`` per day from ``start_close``."""
    session = _TestSession()
    try:
        for i in range(n):
            close = start_close + i * step
            session.add(
                DailyPrice(
                    symbol=symbol,
                    price_date=SIGNAL_DATE + timedelta(days=i),
                    open_price=close - 0.5,
                    high_price=close + 1.0,
                    low_price=close - 1.0,
                    close_price=close,
                    volume=1_000_000 + i,
                    source="test",
                )
            )
        session.commit()
    finally:
        session.close()


def _seed_setup(symbol: str, **overrides) -> None:
    session = _TestSession()
    defaults = dict(
        symbol=symbol,
        snapshot_date=SIGNAL_DATE,
        source="test",
        source_record_count=60,
        current_close=100.0,
        nearest_support=95.0,
        nearest_resistance=130.0,
        sma_50=98.0,
        atr_14=2.0,
        direction="LONG",
        stop_method="ATR",
        target_price=110.0,
        stop_price=95.0,
        risk_per_share=5.0,
        reward_per_share=10.0,
        stock_risk_reward=2.0,
        entry_zone_low=95.0,
        entry_zone_high=102.0,
        data_sufficiency_status="SUFFICIENT",
    )
    defaults.update(overrides)
    try:
        session.add(StockSetup(**defaults))
        session.commit()
    finally:
        session.close()


def _seed_action(symbol: str, label: str) -> None:
    session = _TestSession()
    try:
        session.add(
            ActionSuggestion(
                symbol=symbol,
                snapshot_date=SIGNAL_DATE,
                final_action_label=label,
                instrument_scope="STOCK_ONLY",
                lifecycle_state="READY_FOR_RESEARCH",
                option_expression_status="OPTION_EXPR_NOT_EVALUATED",
                suggested_action_summary="x",
            )
        )
        session.commit()
    finally:
        session.close()


def _seed_rejection(symbol: str, category: str = "HARD_STOCK_REJECTION") -> None:
    session = _TestSession()
    try:
        session.add(
            RejectedCandidate(
                symbol=symbol,
                snapshot_date=SIGNAL_DATE,
                rejection_category=category,
                rejection_severity="HARD_REJECT",
                final_action_label="NO_TRADE",
                lifecycle_state="REJECTED",
                is_rejected_but_interesting=False,
                summary="rejected",
            )
        )
        session.commit()
    finally:
        session.close()


# --- forward returns -------------------------------------------------------


def test_forward_return_unavailable_without_enough_bars() -> None:
    _seed_prices("AMD", 10)  # only 10 bars; horizon 20 unavailable
    session = _TestSession()
    try:
        fr = compute_forward_return(session, "AMD", SIGNAL_DATE, 20)
    finally:
        session.close()
    assert fr.available is False
    assert fr.return_pct is None


def test_forward_return_target_hit_on_rising_series() -> None:
    _seed_prices("AMD", 30, start_close=100.0, step=1.0)
    session = _TestSession()
    try:
        fr = compute_forward_return(
            session, "AMD", SIGNAL_DATE, 20, target_price=110.0, stop_price=95.0,
            direction="LONG",
        )
    finally:
        session.close()
    assert fr.available is True
    assert fr.target_hit is True
    assert fr.stop_hit is False
    assert fr.return_pct > 0


# --- override detection ----------------------------------------------------


def test_detect_override_traded_against_rejection() -> None:
    assert (
        detect_override(system_suggestion_label="NO_TRADE", user_action_type="MANUAL_TRADE")
        == OVERRIDE_TRADED_AGAINST_REJECTION
    )


def test_detect_override_ignored_recommendation() -> None:
    assert (
        detect_override(
            system_suggestion_label="READY_TO_RESEARCH_STOCK_ONLY",
            user_action_type="IGNORE",
        )
        == OVERRIDE_IGNORED_RECOMMENDATION
    )


def test_detect_no_override_when_consistent() -> None:
    assert (
        detect_override(
            system_suggestion_label="READY_TO_RESEARCH_STOCK_ONLY",
            user_action_type="MANUAL_TRADE",
        )
        is None
    )


# --- override outcome classification ---------------------------------------


def test_ignored_recommendation_that_rose_is_system_right_missed() -> None:
    _seed_prices("AMD", 30, start_close=100.0, step=1.0)  # rises -> target hit
    _seed_setup("AMD")
    svc = UserActionService(outcome_horizon=20)
    session = _TestSession()
    try:
        svc.record_action(
            session,
            symbol="AMD",
            action_type="IGNORE",
            system_suggestion_label="READY_TO_RESEARCH_STOCK_ONLY",
            action_date=SIGNAL_DATE,
        )
        svc.track_override_outcomes(session, horizon_days=20)
        outcome = session.query(OverrideOutcome).one()
    finally:
        session.close()
    assert outcome.outcome_classification == OUTCOME_SYSTEM_RIGHT
    assert outcome.is_missed_opportunity is True


def test_traded_against_rejection_that_rose_is_user_right() -> None:
    _seed_prices("AMD", 30, start_close=100.0, step=1.0)
    _seed_setup("AMD")
    svc = UserActionService(outcome_horizon=20)
    session = _TestSession()
    try:
        svc.record_action(
            session,
            symbol="AMD",
            action_type="MANUAL_TRADE",
            system_suggestion_label="NO_TRADE",
            action_date=SIGNAL_DATE,
        )
        svc.track_override_outcomes(session, horizon_days=20)
        outcome = session.query(OverrideOutcome).one()
    finally:
        session.close()
    assert outcome.outcome_classification == OUTCOME_USER_RIGHT


def test_record_action_creates_override_only_when_detected() -> None:
    svc = UserActionService()
    session = _TestSession()
    try:
        # Consistent action -> no override.
        r1 = svc.record_action(
            session,
            symbol="AMD",
            action_type="REVIEW",
            system_suggestion_label="READY_TO_RESEARCH_STOCK_ONLY",
        )
        assert r1.override is None
        # Override action.
        r2 = svc.record_action(
            session,
            symbol="NVDA",
            action_type="MANUAL_TRADE",
            system_suggestion_label="NO_TRADE",
        )
        assert r2.override is not None
        assert session.query(UserOverride).count() == 1
    finally:
        session.close()


# --- signal outcome tracking -----------------------------------------------


def test_signal_outcome_no_option_outcome_when_no_manual_data() -> None:
    _seed_prices("AMD", 40, start_close=100.0, step=1.0)
    _seed_setup("AMD")
    _seed_action("AMD", "READY_TO_RESEARCH_STOCK_ONLY")
    svc = SignalOutcomeService(horizons=(5, 10, 20, 30))
    session = _TestSession()
    try:
        svc.run(session)
        rows = session.query(SignalOutcome).all()
        # 4 horizons (some may be unavailable, but rows still created).
        assert len(rows) == 4
        for row in rows:
            assert row.option_outcome_status == OPTION_OUTCOME_UNAVAILABLE
            assert row.option_return_pct is None
    finally:
        session.close()


def test_signal_outcome_idempotent() -> None:
    _seed_prices("AMD", 40, start_close=100.0, step=1.0)
    _seed_setup("AMD")
    _seed_action("AMD", "READY_TO_RESEARCH_STOCK_ONLY")
    svc = SignalOutcomeService(horizons=(5, 10))
    session = _TestSession()
    try:
        svc.run(session)
        svc.run(session)  # second run must not duplicate
        assert session.query(SignalOutcome).count() == 2
    finally:
        session.close()


# --- rejection outcome tracking --------------------------------------------


def test_rejection_outcome_no_fake_option_backfill() -> None:
    _seed_prices("AMD", 30, start_close=100.0, step=1.0)
    _seed_setup("AMD")
    _seed_rejection("AMD")
    svc = RejectionOutcomeService(horizon_days=20)
    session = _TestSession()
    try:
        svc.run(session)
        row = (
            session.query(RejectionOutcome)
            .filter(RejectionOutcome.source_type == SOURCE_REJECTION)
            .one()
        )
        # No manual option data existed -> option outcome unavailable.
        assert row.would_option_have_worked == WOULD_OPTION_UNAVAILABLE
        assert row.option_data_available is False
    finally:
        session.close()


def test_rejection_outcome_marks_too_strict_when_stock_rose() -> None:
    _seed_prices("AMD", 30, start_close=100.0, step=1.0)  # rises -> target hit
    _seed_setup("AMD")
    _seed_rejection("AMD")
    svc = RejectionOutcomeService(horizon_days=20)
    session = _TestSession()
    try:
        svc.run(session)
        row = session.query(RejectionOutcome).filter(
            RejectionOutcome.source_type == SOURCE_REJECTION
        ).one()
        assert row.is_too_strict is True
        assert row.was_rejection_correct is False
    finally:
        session.close()


def test_rejection_outcome_idempotent() -> None:
    _seed_prices("AMD", 30, start_close=100.0, step=1.0)
    _seed_setup("AMD")
    _seed_rejection("AMD")
    svc = RejectionOutcomeService(horizon_days=20)
    session = _TestSession()
    try:
        svc.run(session)
        svc.run(session)
        assert (
            session.query(RejectionOutcome)
            .filter(RejectionOutcome.source_type == SOURCE_REJECTION)
            .count()
            == 1
        )
    finally:
        session.close()
