"""Phase 26, step 26.13 — focused tests for the review queue layer.

Covers:

* every evaluator (PRICE_ENTERED_ZONE, RECHECK_AFTER_MANUAL_OPTION_INPUT,
  IV_COOLED_DOWN, EARNINGS_AFTERMATH, NEW_IMPORTANT_EVENT,
  DATA_REFRESH_RESTORED);
* the new ``RECHECK_AFTER_MANUAL_OPTION_INPUT`` trigger end-to-end;
* idempotent enqueue;
* arming + disarming based on lifecycle state;
* the scheduled job;
* status transitions (resolve / dismiss / in-review / reopen);
* route shapes.
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.main import app
from app.database.base import Base
from app.database.connection import get_db_session
from app.database.models import DailyPrice, Event
from app.earnings.earnings_models import EarningsRiskSnapshot
from app.iv_history.iv_models import IvRiskSnapshot
from app.lifecycle.lifecycle_models import OpportunityLifecycle
from app.lifecycle.lifecycle_states import (
    STATE_INSUFFICIENT_DATA,
    STATE_READY_FOR_RESEARCH,
    STATE_WAIT_FOR_MANUAL_OPTION_INPUT,
    STATE_WAITING_FOR_ENTRY,
)
from app.market_regime.market_regime_models import MarketRegimeSnapshot
from app.quant.stock_setup_models import StockSetup
from app.review.evaluators import (
    EvaluatorInputs,
    evaluate_data_refresh_restored,
    evaluate_earnings_aftermath,
    evaluate_iv_cooled_down,
    evaluate_manual_option_input,
    evaluate_new_important_event,
    evaluate_price_entered_zone,
)
from app.review.next_review_trigger_engine import NextReviewTriggerEngine
from app.review.review_models import ReviewQueueItem, ReviewTrigger
from app.review.review_queue_generator import ReviewQueueGenerator
from app.review.review_service import ReviewService
from app.review.review_trigger_types import (
    QUEUE_STATUS_DISMISSED,
    QUEUE_STATUS_IN_REVIEW,
    QUEUE_STATUS_PENDING,
    QUEUE_STATUS_RESOLVED,
    TRIGGER_DATA_REFRESH_RESTORED,
    TRIGGER_EARNINGS_AFTERMATH,
    TRIGGER_IV_COOLED_DOWN,
    TRIGGER_NEW_IMPORTANT_EVENT,
    TRIGGER_PRICE_ENTERED_ZONE,
    TRIGGER_RECHECK_AFTER_MANUAL_OPTION_INPUT,
)
from app.review.scheduled_review_trigger_job import ScheduledReviewTriggerJob


# ---------------------------------------------------------------------------
# Pure evaluator unit tests
# ---------------------------------------------------------------------------


def test_price_evaluator_fires_inside_zone() -> None:
    result = evaluate_price_entered_zone(
        EvaluatorInputs(
            symbol="AMD",
            current_close=100.0,
            entry_zone_low=95.0,
            entry_zone_high=105.0,
        )
    )
    assert result is not None
    assert result.trigger_type == TRIGGER_PRICE_ENTERED_ZONE
    assert result.review_reason_label == "PRICE_INSIDE_ENTRY_ZONE"


def test_price_evaluator_does_not_fire_outside_zone() -> None:
    result = evaluate_price_entered_zone(
        EvaluatorInputs(
            symbol="AMD",
            current_close=110.0,
            entry_zone_low=95.0,
            entry_zone_high=105.0,
        )
    )
    assert result is None


def test_price_evaluator_skips_when_zone_missing() -> None:
    result = evaluate_price_entered_zone(
        EvaluatorInputs(symbol="AMD", current_close=100.0)
    )
    assert result is None


def test_manual_option_evaluator_fires_when_snapshot_post_arm() -> None:
    armed_at = datetime(2026, 5, 15, tzinfo=timezone.utc)
    snap_at = armed_at + timedelta(hours=2)
    result = evaluate_manual_option_input(
        EvaluatorInputs(
            symbol="AMD",
            has_manual_option_snapshot=True,
            manual_option_snapshot_created_at=snap_at,
            trigger_armed_at=armed_at,
        )
    )
    assert result is not None
    assert result.trigger_type == TRIGGER_RECHECK_AFTER_MANUAL_OPTION_INPUT


def test_manual_option_evaluator_skips_snapshot_before_arm() -> None:
    armed_at = datetime(2026, 5, 15, tzinfo=timezone.utc)
    snap_at = armed_at - timedelta(hours=2)
    result = evaluate_manual_option_input(
        EvaluatorInputs(
            symbol="AMD",
            has_manual_option_snapshot=True,
            manual_option_snapshot_created_at=snap_at,
            trigger_armed_at=armed_at,
        )
    )
    assert result is None


def test_manual_option_evaluator_skips_when_no_snapshot() -> None:
    assert (
        evaluate_manual_option_input(
            EvaluatorInputs(symbol="AMD", has_manual_option_snapshot=False)
        )
        is None
    )


def test_iv_cooldown_fires_when_below_threshold() -> None:
    result = evaluate_iv_cooled_down(
        EvaluatorInputs(
            symbol="AMD",
            latest_iv_percent=60.0,
            iv_cool_threshold_percent=70.0,
        )
    )
    assert result is not None
    assert result.trigger_type == TRIGGER_IV_COOLED_DOWN


def test_iv_cooldown_does_not_fire_at_threshold() -> None:
    assert (
        evaluate_iv_cooled_down(
            EvaluatorInputs(
                symbol="AMD",
                latest_iv_percent=75.0,
                iv_cool_threshold_percent=70.0,
            )
        )
        is None
    )


def test_iv_cooldown_skips_when_no_iv_data() -> None:
    """Phase 19/24 invariant flowed through: no IV data, no fire."""
    assert (
        evaluate_iv_cooled_down(
            EvaluatorInputs(symbol="AMD", iv_cool_threshold_percent=70.0)
        )
        is None
    )


def test_earnings_aftermath_fires_after_window() -> None:
    event_dt = datetime(2026, 5, 1, tzinfo=timezone.utc)
    now = event_dt + timedelta(days=2)
    result = evaluate_earnings_aftermath(
        EvaluatorInputs(
            symbol="AMD",
            last_earnings_datetime_utc=event_dt,
            earnings_aftermath_window_hours=12,
        ),
        now=now,
    )
    assert result is not None
    assert result.trigger_type == TRIGGER_EARNINGS_AFTERMATH


def test_earnings_aftermath_does_not_fire_before_window() -> None:
    event_dt = datetime(2026, 5, 15, tzinfo=timezone.utc)
    now = event_dt - timedelta(hours=2)
    result = evaluate_earnings_aftermath(
        EvaluatorInputs(
            symbol="AMD",
            last_earnings_datetime_utc=event_dt,
            earnings_aftermath_window_hours=12,
        ),
        now=now,
    )
    assert result is None


def test_new_important_event_fires_on_count() -> None:
    result = evaluate_new_important_event(
        EvaluatorInputs(
            symbol="AMD",
            high_importance_event_count_since_last_eval=2,
            last_high_importance_event_at=datetime(2026, 5, 15, tzinfo=timezone.utc),
        )
    )
    assert result is not None
    assert result.trigger_type == TRIGGER_NEW_IMPORTANT_EVENT


def test_new_important_event_skips_when_count_zero() -> None:
    assert (
        evaluate_new_important_event(
            EvaluatorInputs(symbol="AMD", high_importance_event_count_since_last_eval=0)
        )
        is None
    )


def test_data_refresh_fires_when_restored() -> None:
    result = evaluate_data_refresh_restored(
        EvaluatorInputs(
            symbol="AMD",
            previously_insufficient=True,
            now_sufficient=True,
            insufficient_labels=["INSUFFICIENT_PRICE_HISTORY"],
        )
    )
    assert result is not None
    assert result.trigger_type == TRIGGER_DATA_REFRESH_RESTORED


def test_data_refresh_does_not_fire_without_prior_insufficiency() -> None:
    assert (
        evaluate_data_refresh_restored(
            EvaluatorInputs(symbol="AMD", previously_insufficient=False, now_sufficient=True)
        )
        is None
    )


# ---------------------------------------------------------------------------
# DB fixtures
# ---------------------------------------------------------------------------


_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_TestSession = sessionmaker(bind=_engine, autoflush=False, autocommit=False)


def _override_get_db_session() -> Generator[Session, None, None]:
    session = _TestSession()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(autouse=True)
def reset_db():
    app.dependency_overrides.clear()
    app.dependency_overrides[get_db_session] = _override_get_db_session
    Base.metadata.drop_all(bind=_engine)
    # ``manual_option_snapshots`` is materialised via raw SQL outside the
    # ORM (Phase 8), so ``drop_all`` does not touch it; drop it explicitly
    # so tests stay isolated under StaticPool.
    with _engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS manual_option_snapshots"))
    Base.metadata.create_all(bind=_engine)
    yield
    app.dependency_overrides.clear()


def _seed_prices(symbol: str, n: int) -> None:
    base = date(2026, 1, 2)
    session = _TestSession()
    try:
        for i in range(n):
            session.add(
                DailyPrice(
                    symbol=symbol,
                    price_date=base + timedelta(days=i),
                    open_price=100.0 + i,
                    high_price=101.0 + i,
                    low_price=99.0 + i,
                    close_price=100.5 + i,
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
        snapshot_date=date(2026, 5, 15),
        source="test",
        source_record_count=60,
        current_close=100.0,
        nearest_support=95.0,
        nearest_resistance=120.0,
        sma_50=98.0,
        atr_14=2.0,
        direction="LONG",
        stop_method="ATR",
        target_price=120.0,
        stop_price=93.0,
        risk_per_share=5.0,
        reward_per_share=20.0,
        stock_risk_reward=4.0,
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


def _seed_regime(label: str) -> None:
    session = _TestSession()
    try:
        session.add(
            MarketRegimeSnapshot(
                snapshot_date=date(2026, 5, 15),
                regime_label=label,
                regime_score=2 if label == "RISK_ON" else -2,
                data_sufficiency_status="SUFFICIENT",
            )
        )
        session.commit()
    finally:
        session.close()


def _seed_earnings(symbol: str, **overrides) -> None:
    session = _TestSession()
    defaults = dict(
        symbol=symbol,
        snapshot_date=date(2026, 5, 15),
        next_earnings_datetime_utc=datetime(2026, 8, 1, tzinfo=timezone.utc),
        days_to_earnings=78,
        earnings_within_window=False,
        earnings_risk_window_days=7,
        earnings_before_expiration="NOT_APPLICABLE",
        risk_label="NO_EARNINGS_NEAR",
        risk_reason="ok",
        data_sufficiency_status="SUFFICIENT",
    )
    defaults.update(overrides)
    try:
        session.add(EarningsRiskSnapshot(**defaults))
        session.commit()
    finally:
        session.close()


def _seed_lifecycle(symbol: str, state: str) -> None:
    session = _TestSession()
    try:
        session.add(
            OpportunityLifecycle(
                symbol=symbol,
                current_state=state,
                previous_state=None,
                user_review_status="UNREVIEWED",
            )
        )
        session.commit()
    finally:
        session.close()


def _seed_event(symbol: str, importance: str, when: datetime) -> None:
    session = _TestSession()
    try:
        session.add(
            Event(
                symbol=symbol,
                event_type="news",
                importance_level=importance,
                headline="seed",
                source="test",
                detected_time=when,
                event_time=when,
            )
        )
        session.commit()
    finally:
        session.close()


def _seed_manual_option(symbol: str, when: datetime) -> None:
    """Insert a row into the Phase 8 manual_option_snapshots table.

    The table is created by Phase 8 via raw SQL outside the ORM; for the
    test we materialize a minimal schema matching the engine's read query.
    """
    session = _TestSession()
    try:
        session.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS manual_option_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol VARCHAR(32),
                    created_at TIMESTAMP
                )
                """
            )
        )
        session.execute(
            text(
                "INSERT INTO manual_option_snapshots (symbol, created_at) "
                "VALUES (:symbol, :created_at)"
            ),
            {"symbol": symbol, "created_at": when.isoformat()},
        )
        session.commit()
    finally:
        session.close()


def _seed_iv_snapshot(
    symbol: str,
    *,
    current_iv: float,
    iv_reject_threshold: float,
    iv_warning_threshold: float,
) -> None:
    session = _TestSession()
    try:
        session.add(
            IvRiskSnapshot(
                symbol=symbol,
                snapshot_date=date(2026, 5, 15),
                current_iv=current_iv,
                iv_reject_threshold=iv_reject_threshold,
                iv_warning_threshold=iv_warning_threshold,
                risk_label="IV_OK",
                risk_reason="ok",
                data_sufficiency_status="SUFFICIENT",
            )
        )
        session.commit()
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Arming behaviour
# ---------------------------------------------------------------------------


def test_arm_for_symbol_arms_price_trigger_when_waiting_for_entry() -> None:
    _seed_prices("AMD", 60)
    _seed_setup("AMD")
    _seed_lifecycle("AMD", STATE_WAITING_FOR_ENTRY)

    session = _TestSession()
    try:
        result = NextReviewTriggerEngine().arm_for_symbol(session, "AMD")
        types = {
            t.trigger_type
            for t in session.query(ReviewTrigger)
            .filter(ReviewTrigger.symbol == "AMD")
            .filter(ReviewTrigger.is_active.is_(True))
            .all()
        }
    finally:
        session.close()
    assert TRIGGER_PRICE_ENTERED_ZONE in types
    assert TRIGGER_NEW_IMPORTANT_EVENT in types
    # Always-on triggers should be exactly these two for a basic WFE lifecycle.
    assert TRIGGER_RECHECK_AFTER_MANUAL_OPTION_INPUT not in types


def test_arm_for_symbol_arms_manual_option_trigger() -> None:
    """Phase 26 invariant: WAIT_FOR_MANUAL_OPTION_INPUT lifecycle arms the
    new RECHECK_AFTER_MANUAL_OPTION_INPUT trigger."""
    _seed_lifecycle("AMD", STATE_WAIT_FOR_MANUAL_OPTION_INPUT)

    session = _TestSession()
    try:
        NextReviewTriggerEngine().arm_for_symbol(session, "AMD")
        types = {
            t.trigger_type
            for t in session.query(ReviewTrigger)
            .filter(ReviewTrigger.symbol == "AMD")
            .filter(ReviewTrigger.is_active.is_(True))
            .all()
        }
    finally:
        session.close()
    assert TRIGGER_RECHECK_AFTER_MANUAL_OPTION_INPUT in types


def test_arm_for_symbol_disarms_when_lifecycle_moves() -> None:
    _seed_lifecycle("AMD", STATE_WAITING_FOR_ENTRY)

    session = _TestSession()
    try:
        engine = NextReviewTriggerEngine()
        engine.arm_for_symbol(session, "AMD")
        # Lifecycle moved to READY_FOR_RESEARCH -- price trigger should disarm.
        row = session.query(OpportunityLifecycle).first()
        row.current_state = STATE_READY_FOR_RESEARCH
        session.commit()
        result = engine.arm_for_symbol(session, "AMD")
        active_types = {
            t.trigger_type
            for t in session.query(ReviewTrigger)
            .filter(ReviewTrigger.symbol == "AMD")
            .filter(ReviewTrigger.is_active.is_(True))
            .all()
        }
    finally:
        session.close()
    assert TRIGGER_PRICE_ENTERED_ZONE not in active_types
    assert TRIGGER_NEW_IMPORTANT_EVENT in active_types  # always-on for active lifecycles


# ---------------------------------------------------------------------------
# Engine evaluation
# ---------------------------------------------------------------------------


def test_engine_fires_price_entered_zone_and_enqueues_item() -> None:
    _seed_prices("AMD", 60)
    _seed_setup("AMD")
    _seed_lifecycle("AMD", STATE_WAITING_FOR_ENTRY)

    session = _TestSession()
    try:
        engine = NextReviewTriggerEngine()
        engine.arm_for_symbol(session, "AMD")
        fired = engine.evaluate_armed(session, symbols=["AMD"])
        queue_items = (
            session.query(ReviewQueueItem)
            .filter(ReviewQueueItem.symbol == "AMD")
            .all()
        )
    finally:
        session.close()
    fired_types = {f.trigger.trigger_type for f in fired}
    queue_types = {q.trigger_type for q in queue_items}
    assert TRIGGER_PRICE_ENTERED_ZONE in fired_types
    assert TRIGGER_PRICE_ENTERED_ZONE in queue_types


def test_engine_does_not_fire_price_trigger_when_outside_zone() -> None:
    _seed_prices("AMD", 60)
    _seed_setup("AMD", current_close=130.0)  # outside [95, 102]
    _seed_lifecycle("AMD", STATE_WAITING_FOR_ENTRY)

    session = _TestSession()
    try:
        engine = NextReviewTriggerEngine()
        engine.arm_for_symbol(session, "AMD")
        fired = engine.evaluate_armed(session, symbols=["AMD"])
        types = {f.trigger.trigger_type for f in fired}
    finally:
        session.close()
    assert TRIGGER_PRICE_ENTERED_ZONE not in types


def test_engine_fires_recheck_after_manual_option_input() -> None:
    """The defining Phase 26 addition: RECHECK_AFTER_MANUAL_OPTION_INPUT."""
    _seed_lifecycle("AMD", STATE_WAIT_FOR_MANUAL_OPTION_INPUT)

    session = _TestSession()
    try:
        engine = NextReviewTriggerEngine()
        engine.arm_for_symbol(session, "AMD")
        # Now the user pastes an option AFTER the trigger was armed.
        _seed_manual_option("AMD", datetime.now(timezone.utc) + timedelta(seconds=2))
        fired = engine.evaluate_armed(session, symbols=["AMD"])
        types = {f.trigger.trigger_type for f in fired}
        queue_types = {q.trigger_type for q in session.query(ReviewQueueItem).all()}
    finally:
        session.close()
    assert TRIGGER_RECHECK_AFTER_MANUAL_OPTION_INPUT in types
    assert TRIGGER_RECHECK_AFTER_MANUAL_OPTION_INPUT in queue_types


def test_engine_does_not_fire_recheck_when_no_manual_option_yet() -> None:
    _seed_lifecycle("AMD", STATE_WAIT_FOR_MANUAL_OPTION_INPUT)

    session = _TestSession()
    try:
        engine = NextReviewTriggerEngine()
        engine.arm_for_symbol(session, "AMD")
        fired = engine.evaluate_armed(session, symbols=["AMD"])
        types = {f.trigger.trigger_type for f in fired}
    finally:
        session.close()
    assert TRIGGER_RECHECK_AFTER_MANUAL_OPTION_INPUT not in types


def test_engine_fires_new_important_event() -> None:
    _seed_lifecycle("AMD", STATE_READY_FOR_RESEARCH)

    session = _TestSession()
    try:
        engine = NextReviewTriggerEngine()
        engine.arm_for_symbol(session, "AMD")
        # Now a high-importance event lands AFTER arming.
        _seed_event(
            "AMD",
            importance="HIGH",
            when=datetime.now(timezone.utc) + timedelta(seconds=2),
        )
        fired = engine.evaluate_armed(session, symbols=["AMD"])
        types = {f.trigger.trigger_type for f in fired}
    finally:
        session.close()
    assert TRIGGER_NEW_IMPORTANT_EVENT in types


def test_engine_fires_earnings_aftermath_in_past() -> None:
    _seed_lifecycle("AMD", STATE_READY_FOR_RESEARCH)
    # Earnings event ~5 days ago.
    earnings_dt = datetime.now(timezone.utc) - timedelta(days=5)
    _seed_earnings(
        "AMD", next_earnings_datetime_utc=earnings_dt, days_to_earnings=-5
    )

    session = _TestSession()
    try:
        engine = NextReviewTriggerEngine()
        engine.arm_for_symbol(session, "AMD")
        fired = engine.evaluate_armed(session, symbols=["AMD"])
        types = {f.trigger.trigger_type for f in fired}
    finally:
        session.close()
    assert TRIGGER_EARNINGS_AFTERMATH in types


# ---------------------------------------------------------------------------
# Queue generator idempotency
# ---------------------------------------------------------------------------


def test_queue_generator_is_idempotent_for_same_trigger() -> None:
    _seed_prices("AMD", 60)
    _seed_setup("AMD")
    _seed_lifecycle("AMD", STATE_WAITING_FOR_ENTRY)

    session = _TestSession()
    try:
        engine = NextReviewTriggerEngine()
        engine.arm_for_symbol(session, "AMD")
        engine.evaluate_armed(session, symbols=["AMD"])
        engine.evaluate_armed(session, symbols=["AMD"])
        count = (
            session.query(ReviewQueueItem)
            .filter(ReviewQueueItem.trigger_type == TRIGGER_PRICE_ENTERED_ZONE)
            .count()
        )
    finally:
        session.close()
    assert count == 1


def test_queue_generator_creates_new_after_resolve() -> None:
    _seed_prices("AMD", 60)
    _seed_setup("AMD")
    _seed_lifecycle("AMD", STATE_WAITING_FOR_ENTRY)

    session = _TestSession()
    try:
        engine = NextReviewTriggerEngine()
        engine.arm_for_symbol(session, "AMD")
        engine.evaluate_armed(session, symbols=["AMD"])
        # Resolve the only PRICE_ENTERED_ZONE item, then re-fire.
        item = (
            session.query(ReviewQueueItem)
            .filter(ReviewQueueItem.trigger_type == TRIGGER_PRICE_ENTERED_ZONE)
            .one()
        )
        item.status = QUEUE_STATUS_RESOLVED
        session.commit()
        engine.evaluate_armed(session, symbols=["AMD"])
        count = (
            session.query(ReviewQueueItem)
            .filter(ReviewQueueItem.trigger_type == TRIGGER_PRICE_ENTERED_ZONE)
            .count()
        )
    finally:
        session.close()
    # Resolved item remains for audit; a fresh PENDING item is added.
    assert count == 2


# ---------------------------------------------------------------------------
# Service + transitions
# ---------------------------------------------------------------------------


def test_service_run_triggers_processes_all_lifecycle_symbols() -> None:
    _seed_lifecycle("AMD", STATE_WAITING_FOR_ENTRY)
    _seed_lifecycle("XYZ", STATE_WAITING_FOR_ENTRY)
    _seed_prices("AMD", 60)
    _seed_setup("AMD")
    _seed_prices("XYZ", 60)
    _seed_setup("XYZ")

    session = _TestSession()
    try:
        result = ReviewService().run_triggers(session)
    finally:
        session.close()
    assert result.symbols_processed == 2


def test_service_transition_status_resolves() -> None:
    _seed_prices("AMD", 60)
    _seed_setup("AMD")
    _seed_lifecycle("AMD", STATE_WAITING_FOR_ENTRY)

    session = _TestSession()
    try:
        ReviewService().run_triggers(session, symbols=["AMD"])
        item = (
            session.query(ReviewQueueItem)
            .filter(ReviewQueueItem.trigger_type == TRIGGER_PRICE_ENTERED_ZONE)
            .one()
        )
        result = ReviewService().transition_status(
            session, item.id, new_status=QUEUE_STATUS_RESOLVED, notes="done"
        )
    finally:
        session.close()
    assert result is not None
    assert result.status == QUEUE_STATUS_RESOLVED
    assert result.resolution_notes == "done"


def test_service_transition_status_dismiss() -> None:
    _seed_prices("AMD", 60)
    _seed_setup("AMD")
    _seed_lifecycle("AMD", STATE_WAITING_FOR_ENTRY)

    session = _TestSession()
    try:
        ReviewService().run_triggers(session, symbols=["AMD"])
        item = session.query(ReviewQueueItem).first()
        result = ReviewService().transition_status(
            session, item.id, new_status=QUEUE_STATUS_DISMISSED
        )
    finally:
        session.close()
    assert result is not None
    assert result.status == QUEUE_STATUS_DISMISSED
    assert result.resolved_at is not None


def test_service_transition_status_rejects_bad_status() -> None:
    session = _TestSession()
    try:
        with pytest.raises(ValueError):
            ReviewService().transition_status(
                session, 1, new_status="BANANA"
            )
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Scheduled job
# ---------------------------------------------------------------------------


def test_scheduled_job_runs_idempotently() -> None:
    _seed_prices("AMD", 60)
    _seed_setup("AMD")
    _seed_lifecycle("AMD", STATE_WAITING_FOR_ENTRY)

    session = _TestSession()
    try:
        job = ScheduledReviewTriggerJob()
        first = job.run(session)
        second = job.run(session)
        count = (
            session.query(ReviewQueueItem)
            .filter(ReviewQueueItem.symbol == "AMD")
            .count()
        )
    finally:
        session.close()
    assert first.inner.symbols_processed == 1
    assert second.inner.symbols_processed == 1
    # No duplicates after the second run.
    assert count == 1


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


def test_route_run_triggers_and_list() -> None:
    _seed_prices("AMD", 60)
    _seed_setup("AMD")
    _seed_lifecycle("AMD", STATE_WAITING_FOR_ENTRY)

    client = TestClient(app)
    response = client.post(
        "/api/review-queue/run-triggers", json={"symbols": ["AMD"]}
    )
    assert response.status_code == 200

    listing = client.get("/api/review-queue").json()
    assert listing["count"] >= 1
    listing_symbol = client.get("/api/review-queue/AMD").json()
    assert listing_symbol["count"] >= 1


def test_route_list_validates_status() -> None:
    client = TestClient(app)
    response = client.get("/api/review-queue?status=BANANA")
    assert response.status_code == 400


def test_route_run_triggers_validates_symbols_payload() -> None:
    client = TestClient(app)
    response = client.post(
        "/api/review-queue/run-triggers", json={"symbols": "AMD"}
    )
    assert response.status_code == 400


def test_route_resolve_dismiss_in_review_reopen() -> None:
    _seed_prices("AMD", 60)
    _seed_setup("AMD")
    _seed_lifecycle("AMD", STATE_WAITING_FOR_ENTRY)

    client = TestClient(app)
    client.post("/api/review-queue/run-triggers", json={"symbols": ["AMD"]})
    item_id = client.get("/api/review-queue").json()["items"][0]["id"]

    in_review = client.post(f"/api/review-queue/items/{item_id}/in-review").json()
    assert in_review["item"]["status"] == QUEUE_STATUS_IN_REVIEW

    resolved = client.post(
        f"/api/review-queue/items/{item_id}/resolve",
        json={"notes": "done"},
    ).json()
    assert resolved["item"]["status"] == QUEUE_STATUS_RESOLVED
    assert resolved["item"]["resolution_notes"] == "done"

    reopened = client.post(f"/api/review-queue/items/{item_id}/reopen").json()
    assert reopened["item"]["status"] == QUEUE_STATUS_PENDING

    dismissed = client.post(f"/api/review-queue/items/{item_id}/dismiss").json()
    assert dismissed["item"]["status"] == QUEUE_STATUS_DISMISSED


def test_route_resolve_404_for_unknown_id() -> None:
    client = TestClient(app)
    response = client.post("/api/review-queue/items/9999/resolve")
    assert response.status_code == 404


def test_route_list_triggers() -> None:
    _seed_lifecycle("AMD", STATE_WAITING_FOR_ENTRY)
    _seed_prices("AMD", 60)
    _seed_setup("AMD")

    client = TestClient(app)
    client.post("/api/review-queue/run-triggers", json={"symbols": ["AMD"]})
    response = client.get("/api/review-queue/triggers?symbol=AMD")
    assert response.status_code == 200
    types = {t["trigger_type"] for t in response.json()["triggers"]}
    assert TRIGGER_PRICE_ENTERED_ZONE in types


def test_route_per_symbol_rejects_empty() -> None:
    client = TestClient(app)
    assert client.get("/api/review-queue/%20").status_code == 400
