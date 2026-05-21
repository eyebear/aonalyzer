"""Phase 19-26 cross-layer invariant tests.

The Phase 19-26 cycle put a single rule on the system: **missing option
data must never block, reject, freeze, or queue-review a stock-only
candidate**. Every individual phase has tests for its own layer; this
file pins the invariant *end-to-end* by running a healthy stock symbol
through every layer (Phase 19 sufficiency, Phase 20 hard filters,
Phase 21 decision, Phase 22 action package, Phase 23 rejection,
Phase 24 do-not-touch, Phase 25 lifecycle, Phase 26 review triggers)
with no option data supplied and asserting:

* the data sufficiency gate allows the stock decision;
* the hard filter gate allows the stock decision;
* the Phase 21 final label is ``READY_TO_RESEARCH_STOCK_ONLY``;
* the Phase 22 lifecycle state is ``READY_FOR_RESEARCH``;
* the Phase 23 classification is ``NOT_REJECTED``;
* the Phase 24 freeze classifier returns ``NO_FREEZE``;
* the Phase 25 lifecycle row carries ``READY_FOR_RESEARCH``;
* the Phase 26 trigger engine does not arm the manual-option trigger.

A second test exercises the explicit "option analysis requested but
none supplied" path and asserts the system surfaces
``OPTION_DATA_NOT_AVAILABLE`` / ``WAIT_FOR_MANUAL_OPTION_INPUT`` /
``RECHECK_AFTER_MANUAL_OPTION_INPUT`` cleanly across the same layers
*without* writing a rejection or freeze row.
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.action.action_labels import LIFECYCLE_READY_FOR_RESEARCH
from app.action.action_service import ActionSuggestionService
from app.api.main import app
from app.database.base import Base
from app.database.connection import get_db_session
from app.database.models import DailyPrice
from app.decision.decision_labels import (
    OPTION_DATA_NOT_AVAILABLE,
    READY_TO_RESEARCH_STOCK_ONLY,
)
from app.decision.decision_service import DecisionService
from app.earnings.earnings_models import EarningsRiskSnapshot
from app.lifecycle.lifecycle_models import OpportunityLifecycle
from app.lifecycle.lifecycle_service import LifecycleService
from app.lifecycle.lifecycle_states import (
    STATE_READY_FOR_RESEARCH,
    STATE_WAIT_FOR_MANUAL_OPTION_INPUT,
)
from app.market_regime.market_regime_models import MarketRegimeSnapshot
from app.quant.stock_setup_models import StockSetup
from app.rejection.rejection_categories import (
    CATEGORY_NOT_REJECTED,
    SEVERITY_NOT_REJECTED,
)
from app.rejection.rejection_models import RejectedCandidate
from app.rejection.rejection_service import RejectionService
from app.review.review_models import ReviewQueueItem, ReviewTrigger
from app.review.review_service import ReviewService
from app.review.review_trigger_types import (
    TRIGGER_RECHECK_AFTER_MANUAL_OPTION_INPUT,
)
from app.risk_control.do_not_touch_classifier import (
    DECISION_NO_FREEZE,
)
from app.risk_control.do_not_touch_models import DoNotTouchItem
from app.risk_control.do_not_touch_service import DoNotTouchService


# ---------------------------------------------------------------------------
# Fixtures
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


def _seed_healthy_amd() -> None:
    """Seed every upstream row needed for a healthy stock-only candidate."""
    base = date(2026, 1, 2)
    session = _TestSession()
    try:
        for i in range(60):
            session.add(
                DailyPrice(
                    symbol="AMD",
                    price_date=base + timedelta(days=i),
                    open_price=100.0 + i,
                    high_price=101.0 + i,
                    low_price=99.0 + i,
                    close_price=100.5 + i,
                    volume=1_000_000 + i,
                    source="test",
                )
            )
        session.add(
            StockSetup(
                symbol="AMD",
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
        )
        session.add(
            MarketRegimeSnapshot(
                snapshot_date=date(2026, 5, 15),
                regime_label="RISK_ON",
                regime_score=2,
                data_sufficiency_status="SUFFICIENT",
            )
        )
        session.add(
            EarningsRiskSnapshot(
                symbol="AMD",
                snapshot_date=date(2026, 5, 15),
                next_earnings_datetime_utc=datetime(
                    2026, 8, 1, tzinfo=timezone.utc
                ),
                days_to_earnings=78,
                earnings_within_window=False,
                earnings_risk_window_days=7,
                earnings_before_expiration="NOT_APPLICABLE",
                risk_label="NO_EARNINGS_NEAR",
                risk_reason="ok",
                data_sufficiency_status="SUFFICIENT",
            )
        )
        session.commit()
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Invariant 1: missing option data without ``option_data_requested``
# never blocks, rejects, freezes, or queues anything
# ---------------------------------------------------------------------------


def test_missing_option_data_passes_clean_through_all_phases() -> None:
    """The defining Phase 19-26 invariant.

    A healthy stock-only candidate with no option data and
    ``option_data_requested=False`` must reach the lifecycle in
    ``READY_FOR_RESEARCH`` and produce no rejection / freeze / review
    rows for the missing-option condition.
    """
    _seed_healthy_amd()
    session = _TestSession()
    try:
        # --- Phase 21 ----------------------------------------------------
        decision = DecisionService().evaluate_symbol(
            session, "AMD", option_data_requested=False, persist=False
        )
        assert decision.decision.final_label == READY_TO_RESEARCH_STOCK_ONLY

        # --- Phase 22 ----------------------------------------------------
        action_eval = ActionSuggestionService().evaluate_symbol(
            session, "AMD", option_data_requested=False, persist=True
        )
        assert action_eval.package.lifecycle_state == LIFECYCLE_READY_FOR_RESEARCH
        assert action_eval.package.manual_option_input_needed is False
        assert action_eval.package.option_contract_criteria is None

        # --- Phase 23 ----------------------------------------------------
        rejection_eval = RejectionService().evaluate_symbol(
            session, "AMD", option_data_requested=False, persist=True
        )
        assert (
            rejection_eval.classification.rejection_category
            == CATEGORY_NOT_REJECTED
        )
        assert (
            rejection_eval.classification.rejection_severity
            == SEVERITY_NOT_REJECTED
        )
        assert session.query(RejectedCandidate).count() == 0  # no rejection row

        # --- Phase 24 ----------------------------------------------------
        dnt_eval = DoNotTouchService().evaluate_symbol(
            session, "AMD", option_data_requested=False, persist=True
        )
        assert dnt_eval.recommendation.decision == DECISION_NO_FREEZE
        assert session.query(DoNotTouchItem).count() == 0  # no freeze row

        # --- Phase 25 ----------------------------------------------------
        lifecycle = LifecycleService().evaluate_symbol(session, "AMD")
        assert lifecycle.lifecycle.current_state == STATE_READY_FOR_RESEARCH

        # --- Phase 26 ----------------------------------------------------
        review_run = ReviewService().run_triggers(session, symbols=["AMD"])
        # The manual-option trigger MUST NOT be armed for a stock-only
        # candidate; the trigger engine only arms it when the lifecycle is
        # WAIT_FOR_MANUAL_OPTION_INPUT.
        armed_types = {
            t.trigger_type
            for t in session.query(ReviewTrigger)
            .filter(ReviewTrigger.symbol == "AMD")
            .filter(ReviewTrigger.is_active.is_(True))
            .all()
        }
        assert TRIGGER_RECHECK_AFTER_MANUAL_OPTION_INPUT not in armed_types
        # The queue must not have a RECHECK_AFTER_MANUAL_OPTION_INPUT item.
        queue_types = {
            q.trigger_type
            for q in session.query(ReviewQueueItem)
            .filter(ReviewQueueItem.symbol == "AMD")
            .all()
        }
        assert TRIGGER_RECHECK_AFTER_MANUAL_OPTION_INPUT not in queue_types

        # Sanity: the run did process the symbol.
        assert review_run.symbols_processed == 1
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Invariant 2: option requested but missing -- surfaces cleanly, still
# does not reject or freeze
# ---------------------------------------------------------------------------


def test_option_requested_but_missing_surfaces_cleanly() -> None:
    """``option_data_requested=True`` with no option pasted should land
    in ``OPTION_DATA_NOT_AVAILABLE`` / ``WAIT_FOR_MANUAL_OPTION_INPUT``,
    and the Phase 26 engine should arm (and ultimately fire, once the
    user pastes a contract) the ``RECHECK_AFTER_MANUAL_OPTION_INPUT``
    trigger. No rejection / freeze rows are written for the missing-
    option state itself.
    """
    _seed_healthy_amd()
    session = _TestSession()
    try:
        # Phase 21 / 22.
        decision = DecisionService().evaluate_symbol(
            session, "AMD", option_data_requested=True, persist=False
        )
        assert decision.decision.final_label == OPTION_DATA_NOT_AVAILABLE

        package = ActionSuggestionService().evaluate_symbol(
            session, "AMD", option_data_requested=True, persist=True
        ).package
        assert package.manual_option_input_needed is True
        assert package.option_contract_criteria is not None

        # Phase 23: NOT a rejection.
        rejection = RejectionService().evaluate_symbol(
            session, "AMD", option_data_requested=True, persist=True
        )
        assert rejection.classification.rejection_category == CATEGORY_NOT_REJECTED
        assert session.query(RejectedCandidate).count() == 0

        # Phase 24: NOT a freeze.
        dnt = DoNotTouchService().evaluate_symbol(
            session, "AMD", option_data_requested=True, persist=True
        )
        assert dnt.recommendation.decision == DECISION_NO_FREEZE
        assert session.query(DoNotTouchItem).count() == 0

        # Phase 25: lifecycle is the new WAIT_FOR_MANUAL_OPTION_INPUT.
        lifecycle = LifecycleService().evaluate_symbol(
            session, "AMD", option_data_requested=True
        )
        assert (
            lifecycle.lifecycle.current_state
            == STATE_WAIT_FOR_MANUAL_OPTION_INPUT
        )

        # Phase 26: the manual-option trigger is armed but does not
        # auto-fire (no manual option snapshot exists yet).
        ReviewService().run_triggers(session, symbols=["AMD"])
        armed = (
            session.query(ReviewTrigger)
            .filter(ReviewTrigger.symbol == "AMD")
            .filter(ReviewTrigger.is_active.is_(True))
            .filter(
                ReviewTrigger.trigger_type
                == TRIGGER_RECHECK_AFTER_MANUAL_OPTION_INPUT
            )
            .one_or_none()
        )
        assert armed is not None
        queued = (
            session.query(ReviewQueueItem)
            .filter(ReviewQueueItem.symbol == "AMD")
            .filter(
                ReviewQueueItem.trigger_type
                == TRIGGER_RECHECK_AFTER_MANUAL_OPTION_INPUT
            )
            .all()
        )
        assert queued == []  # no fire until the user pastes an option
    finally:
        session.close()


def test_no_lifecycle_row_means_no_phase26_state_change() -> None:
    """Re-running Phase 26 on a symbol with no lifecycle row is a no-op:
    no armed triggers, no queue items, no exceptions."""
    session = _TestSession()
    try:
        result = ReviewService().run_triggers(session)
    finally:
        session.close()
    assert result.symbols_processed == 0
    assert result.queue_items_created == 0
    assert result.queue_items_refreshed == 0


def test_decision_service_does_not_call_hard_filter_without_sufficiency() -> None:
    """Phase 21 always runs the Phase 19 gate first, by construction.
    Re-confirm by reading the decision's ``sufficiency_decision``: it
    must be populated for every decision returned by the service.
    """
    _seed_healthy_amd()
    session = _TestSession()
    try:
        decision = DecisionService().evaluate_symbol(
            session, "AMD", persist=False
        ).decision
    finally:
        session.close()
    assert decision.sufficiency_decision is not None
    assert decision.sufficiency_decision.stock_decision_status is not None
    assert decision.sufficiency_decision.symbol == "AMD"
