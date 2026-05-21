"""Phase 25, step 25.12 — focused tests for the opportunity lifecycle layer.

Covers:

* the new ``WAIT_FOR_MANUAL_OPTION_INPUT`` state (normalised from the
  Phase 22 ``AWAITING_OPTION_DATA``);
* every transition kind (FIRST_OBSERVATION / UPGRADE / DOWNGRADE /
  REACTIVATION / DATA_RESTORED / DATA_LOST / OPTION_INPUT_NEEDED /
  OPTION_INPUT_SATISFIED / NO_CHANGE);
* idempotent re-evaluation;
* the reactivation engine + service flow;
* the user-review tracker;
* the update job;
* the route surface (list, per-symbol get/evaluate, review, history,
  update, reactivate).
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.action.action_labels import (
    LIFECYCLE_AWAITING_OPTION_DATA,
    LIFECYCLE_READY_FOR_RESEARCH,
    LIFECYCLE_REJECTED,
    LIFECYCLE_WATCHING,
)
from app.api.main import app
from app.database.base import Base
from app.database.connection import get_db_session
from app.database.models import DailyPrice
from app.earnings.earnings_models import EarningsRiskSnapshot
from app.lifecycle.lifecycle_history_writer import LifecycleHistoryWriter
from app.lifecycle.lifecycle_memory_bridge import (
    LifecycleLesson,
    LifecycleMemoryBridge,
)
from app.lifecycle.lifecycle_models import (
    OpportunityLifecycle,
    OpportunityStateTransition,
)
from app.lifecycle.lifecycle_service import LifecycleService
from app.lifecycle.lifecycle_states import (
    PHASE22_TO_PHASE25,
    REVIEW_DISMISSED,
    REVIEW_REVIEWED,
    REVIEW_UNREVIEWED,
    STATE_INSUFFICIENT_DATA,
    STATE_READY_FOR_RESEARCH,
    STATE_REJECTED,
    STATE_WAIT_FOR_MANUAL_OPTION_INPUT,
    STATE_WATCHING,
    SOURCE_PHASE_PHASE22,
    TRIGGER_SYSTEM_EVALUATION,
    normalize_phase22_state,
)
from app.lifecycle.lifecycle_update_job import LifecycleUpdateJob
from app.lifecycle.opportunity_state_manager import OpportunityStateManager
from app.lifecycle.reactivation_engine import ReactivationEngine
from app.lifecycle.state_reason_builder import build_transition_reason
from app.lifecycle.state_transition_engine import (
    KIND_DATA_LOST,
    KIND_DATA_RESTORED,
    KIND_DOWNGRADE,
    KIND_FIRST_OBSERVATION,
    KIND_NO_CHANGE,
    KIND_OPTION_INPUT_NEEDED,
    KIND_OPTION_INPUT_SATISFIED,
    KIND_REACTIVATION,
    KIND_UPGRADE,
    plan_transition,
)
from app.lifecycle.user_review_state_tracker import UserReviewStateTracker
from app.market_regime.market_regime_models import MarketRegimeSnapshot
from app.quant.stock_setup_models import StockSetup


# ---------------------------------------------------------------------------
# State-machine unit tests (pure logic)
# ---------------------------------------------------------------------------


def test_normalize_phase22_awaiting_option_data_maps_to_phase25() -> None:
    """The defining Phase 25 addition: WAIT_FOR_MANUAL_OPTION_INPUT."""
    assert (
        normalize_phase22_state(LIFECYCLE_AWAITING_OPTION_DATA)
        == STATE_WAIT_FOR_MANUAL_OPTION_INPUT
    )
    # Other Phase 22 states pass through with the same string value.
    assert normalize_phase22_state(LIFECYCLE_READY_FOR_RESEARCH) == STATE_READY_FOR_RESEARCH
    assert normalize_phase22_state(LIFECYCLE_REJECTED) == STATE_REJECTED


def test_phase22_to_phase25_mapping_is_total() -> None:
    # Every Phase 22 lifecycle state has a Phase 25 mapping.
    from app.action.action_labels import (
        LIFECYCLE_INSUFFICIENT_DATA,
        LIFECYCLE_READY_FOR_RESEARCH,
        LIFECYCLE_REJECTED,
        LIFECYCLE_WAITING_FOR_ENTRY,
        LIFECYCLE_WATCHING,
    )

    every = {
        LIFECYCLE_READY_FOR_RESEARCH,
        LIFECYCLE_WATCHING,
        LIFECYCLE_WAITING_FOR_ENTRY,
        LIFECYCLE_AWAITING_OPTION_DATA,
        LIFECYCLE_REJECTED,
        LIFECYCLE_INSUFFICIENT_DATA,
    }
    assert every.issubset(set(PHASE22_TO_PHASE25.keys()))


def test_plan_transition_first_observation() -> None:
    plan = plan_transition(
        current_state=None,
        target_state_phase22=LIFECYCLE_READY_FOR_RESEARCH,
    )
    assert plan.kind == KIND_FIRST_OBSERVATION
    assert plan.is_change is True
    assert plan.to_state == STATE_READY_FOR_RESEARCH


def test_plan_transition_no_change() -> None:
    plan = plan_transition(
        current_state=STATE_WATCHING,
        target_state_phase22=LIFECYCLE_WATCHING,
    )
    assert plan.kind == KIND_NO_CHANGE
    assert plan.is_change is False


def test_plan_transition_upgrade() -> None:
    plan = plan_transition(
        current_state=STATE_WATCHING,
        target_state_phase22=LIFECYCLE_READY_FOR_RESEARCH,
    )
    assert plan.kind == KIND_UPGRADE


def test_plan_transition_downgrade() -> None:
    plan = plan_transition(
        current_state=STATE_READY_FOR_RESEARCH,
        target_state_phase22=LIFECYCLE_WATCHING,
    )
    assert plan.kind == KIND_DOWNGRADE


def test_plan_transition_reactivation_from_rejected() -> None:
    plan = plan_transition(
        current_state=STATE_REJECTED,
        target_state_phase22=LIFECYCLE_READY_FOR_RESEARCH,
    )
    assert plan.kind == KIND_REACTIVATION


def test_plan_transition_option_input_needed() -> None:
    plan = plan_transition(
        current_state=STATE_READY_FOR_RESEARCH,
        target_state_phase22=LIFECYCLE_AWAITING_OPTION_DATA,
    )
    assert plan.kind == KIND_OPTION_INPUT_NEEDED
    assert plan.to_state == STATE_WAIT_FOR_MANUAL_OPTION_INPUT


def test_plan_transition_option_input_satisfied() -> None:
    plan = plan_transition(
        current_state=STATE_WAIT_FOR_MANUAL_OPTION_INPUT,
        target_state_phase22=LIFECYCLE_READY_FOR_RESEARCH,
    )
    assert plan.kind == KIND_OPTION_INPUT_SATISFIED


def test_plan_transition_data_restored() -> None:
    plan = plan_transition(
        current_state=STATE_INSUFFICIENT_DATA,
        target_state_phase22=LIFECYCLE_WATCHING,
    )
    assert plan.kind == KIND_DATA_RESTORED


def test_plan_transition_data_lost() -> None:
    from app.action.action_labels import LIFECYCLE_INSUFFICIENT_DATA

    plan = plan_transition(
        current_state=STATE_WATCHING,
        target_state_phase22=LIFECYCLE_INSUFFICIENT_DATA,
    )
    assert plan.kind == KIND_DATA_LOST


def test_reason_builder_has_summary_for_each_kind() -> None:
    plan = plan_transition(
        current_state=STATE_WATCHING,
        target_state_phase22=LIFECYCLE_READY_FOR_RESEARCH,
    )
    reason = build_transition_reason(plan, final_action_label="X")
    assert reason.label == "UPGRADE"
    assert STATE_READY_FOR_RESEARCH in reason.summary
    assert "X" in reason.summary


# ---------------------------------------------------------------------------
# DB fixtures and seeding
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
    Base.metadata.create_all(bind=_engine)
    yield
    app.dependency_overrides.clear()


def _price_rows(n: int) -> list[dict]:
    base = date(2026, 1, 2)
    return [
        {
            "date": base + timedelta(days=i),
            "open": 100.0 + i,
            "high": 101.0 + i,
            "low": 99.0 + i,
            "close": 100.5 + i,
            "volume": 1_000_000 + i,
        }
        for i in range(n)
    ]


def _seed_prices(symbol: str, n: int) -> None:
    session = _TestSession()
    try:
        for row in _price_rows(n):
            session.add(
                DailyPrice(
                    symbol=symbol,
                    price_date=row["date"],
                    open_price=row["open"],
                    high_price=row["high"],
                    low_price=row["low"],
                    close_price=row["close"],
                    volume=row["volume"],
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


# ---------------------------------------------------------------------------
# State manager + history writer
# ---------------------------------------------------------------------------


def test_state_manager_creates_first_observation_and_logs_transition() -> None:
    manager = OpportunityStateManager()
    plan = plan_transition(
        current_state=None,
        target_state_phase22=LIFECYCLE_READY_FOR_RESEARCH,
    )
    reason = build_transition_reason(plan, final_action_label="X")
    session = _TestSession()
    try:
        result = manager.apply_transition(
            db=session,
            symbol="amd",
            plan=plan,
            reason_label=reason.label,
            reason_summary=reason.summary,
            triggered_by=TRIGGER_SYSTEM_EVALUATION,
            source_phase=SOURCE_PHASE_PHASE22,
            final_action_label="X",
        )
        rows = session.query(OpportunityLifecycle).all()
        transitions = session.query(OpportunityStateTransition).all()
    finally:
        session.close()
    assert len(rows) == 1
    assert rows[0].symbol == "AMD"
    assert rows[0].current_state == STATE_READY_FOR_RESEARCH
    assert rows[0].previous_state is None
    assert result.transition_id is not None
    assert len(transitions) == 1
    assert transitions[0].transition_reason_label == "FIRST_OBSERVATION"


def test_state_manager_no_change_does_not_log_transition() -> None:
    manager = OpportunityStateManager()
    plan_init = plan_transition(
        current_state=None,
        target_state_phase22=LIFECYCLE_READY_FOR_RESEARCH,
    )
    plan_same = plan_transition(
        current_state=STATE_READY_FOR_RESEARCH,
        target_state_phase22=LIFECYCLE_READY_FOR_RESEARCH,
    )
    reason1 = build_transition_reason(plan_init)
    reason2 = build_transition_reason(plan_same)
    session = _TestSession()
    try:
        manager.apply_transition(
            db=session,
            symbol="AMD",
            plan=plan_init,
            reason_label=reason1.label,
            reason_summary=reason1.summary,
            triggered_by=TRIGGER_SYSTEM_EVALUATION,
            source_phase=SOURCE_PHASE_PHASE22,
        )
        res = manager.apply_transition(
            db=session,
            symbol="AMD",
            plan=plan_same,
            reason_label=reason2.label,
            reason_summary=reason2.summary,
            triggered_by=TRIGGER_SYSTEM_EVALUATION,
            source_phase=SOURCE_PHASE_PHASE22,
        )
        transitions = session.query(OpportunityStateTransition).count()
    finally:
        session.close()
    assert res.transition_id is None
    assert transitions == 1


def test_state_manager_real_transition_resets_review_status() -> None:
    manager = OpportunityStateManager()
    init_plan = plan_transition(
        current_state=None,
        target_state_phase22=LIFECYCLE_READY_FOR_RESEARCH,
    )
    reason1 = build_transition_reason(init_plan)
    session = _TestSession()
    try:
        manager.apply_transition(
            db=session,
            symbol="AMD",
            plan=init_plan,
            reason_label=reason1.label,
            reason_summary=reason1.summary,
            triggered_by=TRIGGER_SYSTEM_EVALUATION,
            source_phase=SOURCE_PHASE_PHASE22,
        )
        manager.mark_reviewed(session, "AMD", review_status=REVIEW_REVIEWED)
        # Now a real state change.
        next_plan = plan_transition(
            current_state=STATE_READY_FOR_RESEARCH,
            target_state_phase22=LIFECYCLE_WATCHING,
        )
        reason2 = build_transition_reason(next_plan)
        manager.apply_transition(
            db=session,
            symbol="AMD",
            plan=next_plan,
            reason_label=reason2.label,
            reason_summary=reason2.summary,
            triggered_by=TRIGGER_SYSTEM_EVALUATION,
            source_phase=SOURCE_PHASE_PHASE22,
        )
        row = session.query(OpportunityLifecycle).first()
    finally:
        session.close()
    assert row.user_review_status == REVIEW_UNREVIEWED


# ---------------------------------------------------------------------------
# Service end-to-end
# ---------------------------------------------------------------------------


def test_service_evaluate_first_time_creates_lifecycle() -> None:
    _seed_prices("AMD", 60)
    _seed_setup("AMD")
    _seed_regime("RISK_ON")
    _seed_earnings("AMD")

    session = _TestSession()
    try:
        evaluation = LifecycleService().evaluate_symbol(session, "AMD")
        row = session.query(OpportunityLifecycle).first()
    finally:
        session.close()
    assert evaluation.update.plan.kind == KIND_FIRST_OBSERVATION
    assert row is not None
    assert row.current_state == STATE_READY_FOR_RESEARCH


def test_service_option_data_requested_maps_to_wait_for_manual_option_input() -> None:
    """Phase 25 invariant: AWAITING_OPTION_DATA from Phase 22 becomes the
    new ``WAIT_FOR_MANUAL_OPTION_INPUT`` Phase 25 state."""
    _seed_prices("AMD", 60)
    _seed_setup("AMD")
    _seed_regime("RISK_ON")
    _seed_earnings("AMD")

    session = _TestSession()
    try:
        evaluation = LifecycleService().evaluate_symbol(
            session, "AMD", option_data_requested=True
        )
        row = session.query(OpportunityLifecycle).first()
    finally:
        session.close()
    assert row.current_state == STATE_WAIT_FOR_MANUAL_OPTION_INPUT
    assert evaluation.update.plan.to_state == STATE_WAIT_FOR_MANUAL_OPTION_INPUT


def test_service_idempotent_re_evaluation() -> None:
    _seed_prices("AMD", 60)
    _seed_setup("AMD")
    _seed_regime("RISK_ON")
    _seed_earnings("AMD")

    session = _TestSession()
    try:
        service = LifecycleService()
        service.evaluate_symbol(session, "AMD")
        second = service.evaluate_symbol(session, "AMD")
        transitions = session.query(OpportunityStateTransition).count()
    finally:
        session.close()
    assert second.update.plan.kind == KIND_NO_CHANGE
    assert transitions == 1


def test_service_downgrade_after_warning_appears() -> None:
    _seed_prices("AMD", 60)
    _seed_setup("AMD")
    _seed_regime("RISK_ON")
    _seed_earnings("AMD")

    session = _TestSession()
    try:
        service = LifecycleService()
        service.evaluate_symbol(session, "AMD")
        # Now flip regime to RISK_OFF so the next evaluation downgrades.
        # Update the snapshot in place rather than seeding a new one.
        regime = session.query(MarketRegimeSnapshot).first()
        regime.regime_label = "RISK_OFF"
        regime.regime_score = -2
        session.commit()
        second = service.evaluate_symbol(session, "AMD")
        row = session.query(OpportunityLifecycle).first()
    finally:
        session.close()
    assert second.update.plan.kind == KIND_DOWNGRADE
    assert row.current_state == STATE_WATCHING
    assert row.previous_state == STATE_READY_FOR_RESEARCH


def test_service_reactivation_from_rejected_to_active() -> None:
    _seed_prices("AMD", 60)
    _seed_setup("AMD", stock_risk_reward=1.0)  # NO_TRADE => REJECTED
    _seed_regime("RISK_ON")
    _seed_earnings("AMD")

    session = _TestSession()
    try:
        service = LifecycleService()
        service.evaluate_symbol(session, "AMD")
        # Improve the setup so the next evaluation produces an active state.
        setup = session.query(StockSetup).first()
        setup.stock_risk_reward = 4.0
        session.commit()
        reactivations = service.detect_reactivations(session)
        row = session.query(OpportunityLifecycle).first()
    finally:
        session.close()
    assert len(reactivations) == 1
    assert reactivations[0].update.plan.kind == KIND_REACTIVATION
    assert row.current_state in {STATE_READY_FOR_RESEARCH, STATE_WATCHING}
    assert row.last_reactivation_at is not None


def test_service_history_returns_audit_trail() -> None:
    _seed_prices("AMD", 60)
    _seed_setup("AMD")
    _seed_regime("RISK_ON")
    _seed_earnings("AMD")

    session = _TestSession()
    try:
        service = LifecycleService()
        service.evaluate_symbol(session, "AMD")
        # Flip regime to force a downgrade and a second transition.
        regime = session.query(MarketRegimeSnapshot).first()
        regime.regime_label = "RISK_OFF"
        session.commit()
        service.evaluate_symbol(session, "AMD")
        history = service.get_history(session, "AMD")
    finally:
        session.close()
    labels = [r.transition_reason_label for r in history]
    assert "FIRST_OBSERVATION" in labels
    assert "DOWNGRADE" in labels


# ---------------------------------------------------------------------------
# User review tracker
# ---------------------------------------------------------------------------


def test_user_review_tracker_marks_and_logs_transition() -> None:
    _seed_prices("AMD", 60)
    _seed_setup("AMD")
    _seed_regime("RISK_ON")
    _seed_earnings("AMD")

    session = _TestSession()
    try:
        LifecycleService().evaluate_symbol(session, "AMD")
        tracker = UserReviewStateTracker()
        result = tracker.mark(
            session, symbol="AMD", review_status=REVIEW_REVIEWED, notes="ok"
        )
        row = session.query(OpportunityLifecycle).first()
        transitions = session.query(OpportunityStateTransition).all()
    finally:
        session.close()
    assert result["updated"] is True
    assert row.user_review_status == REVIEW_REVIEWED
    review_rows = [
        t for t in transitions if t.transition_reason_label.startswith("USER_")
    ]
    assert len(review_rows) == 1
    assert review_rows[0].transition_reason_label == "USER_REVIEWED"


def test_user_review_tracker_no_lifecycle_returns_false() -> None:
    session = _TestSession()
    try:
        result = UserReviewStateTracker().mark(
            session, symbol="UNKNOWN", review_status=REVIEW_REVIEWED
        )
    finally:
        session.close()
    assert result["updated"] is False


# ---------------------------------------------------------------------------
# Reactivation engine
# ---------------------------------------------------------------------------


def test_reactivation_engine_detects_terminal_to_active() -> None:
    manager = OpportunityStateManager()
    init = plan_transition(
        current_state=None,
        target_state_phase22=LIFECYCLE_REJECTED,
    )
    reason = build_transition_reason(init)
    session = _TestSession()
    try:
        manager.apply_transition(
            db=session,
            symbol="AMD",
            plan=init,
            reason_label=reason.label,
            reason_summary=reason.summary,
            triggered_by=TRIGGER_SYSTEM_EVALUATION,
            source_phase=SOURCE_PHASE_PHASE22,
        )
        engine = ReactivationEngine()
        detected = engine.detect(
            db=session,
            latest_actions={"AMD": LIFECYCLE_READY_FOR_RESEARCH},
        )
    finally:
        session.close()
    assert len(detected.candidates) == 1
    assert detected.candidates[0].current_state == STATE_REJECTED
    assert detected.candidates[0].target_state == STATE_READY_FOR_RESEARCH


def test_reactivation_engine_ignores_active_lifecycles() -> None:
    manager = OpportunityStateManager()
    init = plan_transition(
        current_state=None,
        target_state_phase22=LIFECYCLE_WATCHING,
    )
    reason = build_transition_reason(init)
    session = _TestSession()
    try:
        manager.apply_transition(
            db=session,
            symbol="AMD",
            plan=init,
            reason_label=reason.label,
            reason_summary=reason.summary,
            triggered_by=TRIGGER_SYSTEM_EVALUATION,
            source_phase=SOURCE_PHASE_PHASE22,
        )
        detected = ReactivationEngine().detect(
            db=session,
            latest_actions={"AMD": LIFECYCLE_READY_FOR_RESEARCH},
        )
    finally:
        session.close()
    assert detected.candidates == []


# ---------------------------------------------------------------------------
# Memory bridge
# ---------------------------------------------------------------------------


def test_memory_bridge_writes_lesson_as_transition_row() -> None:
    bridge = LifecycleMemoryBridge()
    session = _TestSession()
    try:
        result = bridge.record_lesson(
            db=session,
            lesson=LifecycleLesson(
                symbol="AMD",
                lesson_label="REGIME_FLIP_UPGRADE",
                summary="Reactivated 12 days after rejection.",
                context={"prior_state": "REJECTED"},
            ),
            current_state=STATE_READY_FOR_RESEARCH,
        )
        rows = session.query(OpportunityStateTransition).all()
    finally:
        session.close()
    assert len(rows) == 1
    assert rows[0].transition_reason_label.startswith("LIFECYCLE_LESSON:")
    assert result["transition_id"] == rows[0].id


# ---------------------------------------------------------------------------
# Update job
# ---------------------------------------------------------------------------


def test_update_job_processes_explicit_symbols() -> None:
    _seed_prices("AMD", 60)
    _seed_setup("AMD")
    _seed_regime("RISK_ON")
    _seed_earnings("AMD")

    session = _TestSession()
    try:
        job = LifecycleUpdateJob()
        result = job.run(session, symbols=["AMD"])
    finally:
        session.close()
    assert result.symbols_processed == 1
    assert result.transitions_recorded == 1  # first observation


def test_update_job_is_idempotent_on_second_run() -> None:
    _seed_prices("AMD", 60)
    _seed_setup("AMD")
    _seed_regime("RISK_ON")
    _seed_earnings("AMD")

    session = _TestSession()
    try:
        job = LifecycleUpdateJob()
        job.run(session, symbols=["AMD"])
        second = job.run(session, symbols=["AMD"])
    finally:
        session.close()
    assert second.symbols_processed == 1
    # Second run is a NO_CHANGE -- no new transition.
    assert second.transitions_recorded == 0


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


def test_route_list_filters_by_state() -> None:
    _seed_prices("AMD", 60)
    _seed_setup("AMD")
    _seed_regime("RISK_ON")
    _seed_earnings("AMD")

    client = TestClient(app)
    client.get("/api/lifecycle/AMD?evaluate=true")  # create row
    listing = client.get(
        f"/api/lifecycle?state={STATE_READY_FOR_RESEARCH}"
    ).json()
    assert listing["count"] == 1
    assert listing["lifecycles"][0]["current_state"] == STATE_READY_FOR_RESEARCH


def test_route_per_symbol_evaluate_creates_lifecycle() -> None:
    _seed_prices("AMD", 60)
    _seed_setup("AMD")
    _seed_regime("RISK_ON")
    _seed_earnings("AMD")

    client = TestClient(app)
    response = client.get("/api/lifecycle/AMD?evaluate=true")
    assert response.status_code == 200
    body = response.json()
    assert body["lifecycle"]["symbol"] == "AMD"
    assert body["lifecycle"]["current_state"] == STATE_READY_FOR_RESEARCH


def test_route_get_without_evaluate_returns_none_for_unknown() -> None:
    client = TestClient(app)
    response = client.get("/api/lifecycle/UNKNOWN?evaluate=false")
    assert response.status_code == 200
    assert response.json()["lifecycle"] is None


def test_route_review_updates_status() -> None:
    _seed_prices("AMD", 60)
    _seed_setup("AMD")
    _seed_regime("RISK_ON")
    _seed_earnings("AMD")

    client = TestClient(app)
    client.get("/api/lifecycle/AMD?evaluate=true")
    response = client.post(
        "/api/lifecycle/AMD/review",
        json={"review_status": "REVIEWED", "notes": "ok"},
    )
    assert response.status_code == 200
    row_after = client.get("/api/lifecycle/AMD?evaluate=false").json()
    assert row_after["lifecycle"]["user_review_status"] == REVIEW_REVIEWED


def test_route_review_rejects_bad_status() -> None:
    _seed_prices("AMD", 60)
    _seed_setup("AMD")
    _seed_regime("RISK_ON")
    _seed_earnings("AMD")

    client = TestClient(app)
    client.get("/api/lifecycle/AMD?evaluate=true")
    response = client.post(
        "/api/lifecycle/AMD/review", json={"review_status": "BANANA"}
    )
    assert response.status_code == 400


def test_route_review_404_when_no_lifecycle() -> None:
    client = TestClient(app)
    response = client.post(
        "/api/lifecycle/UNKNOWN/review",
        json={"review_status": "REVIEWED"},
    )
    assert response.status_code == 404


def test_route_history_returns_audit_trail() -> None:
    _seed_prices("AMD", 60)
    _seed_setup("AMD")
    _seed_regime("RISK_ON")
    _seed_earnings("AMD")

    client = TestClient(app)
    client.get("/api/lifecycle/AMD?evaluate=true")
    response = client.get("/api/lifecycle/history/AMD")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] >= 1
    assert any(
        row["transition_reason_label"] == "FIRST_OBSERVATION"
        for row in body["history"]
    )


def test_route_update_job_runs() -> None:
    _seed_prices("AMD", 60)
    _seed_setup("AMD")
    _seed_regime("RISK_ON")
    _seed_earnings("AMD")

    client = TestClient(app)
    response = client.post("/api/lifecycle/update", json={"symbols": ["AMD"]})
    assert response.status_code == 200
    body = response.json()
    assert body["result"]["symbols_processed"] == 1


def test_route_reactivate_returns_empty_when_no_terminals() -> None:
    _seed_prices("AMD", 60)
    _seed_setup("AMD")
    _seed_regime("RISK_ON")
    _seed_earnings("AMD")

    client = TestClient(app)
    client.get("/api/lifecycle/AMD?evaluate=true")  # active lifecycle
    response = client.post("/api/lifecycle/reactivate", json={})
    assert response.status_code == 200
    assert response.json()["reactivations"] == []


def test_route_rejects_empty_symbol() -> None:
    client = TestClient(app)
    assert client.get("/api/lifecycle/%20").status_code == 400
    assert (
        client.post(
            "/api/lifecycle/%20/review", json={"review_status": "REVIEWED"}
        ).status_code
        == 400
    )


def test_route_update_validates_symbols_payload() -> None:
    client = TestClient(app)
    response = client.post("/api/lifecycle/update", json={"symbols": "AMD"})
    assert response.status_code == 400
