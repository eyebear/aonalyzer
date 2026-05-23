"""Phase 24, step 24.10 — focused tests for the Do-Not-Touch layer.

Covers:

* the two Phase 24 invariants:
    - missing option data alone never creates a freeze;
    - extreme pasted option risk does create a freeze;
* every freeze category is triggered correctly;
* freeze + release + expiration mutate the active and history tables;
* idempotent freeze and severity upgrade;
* the freeze-expiration monitor releases expired items;
* routes (list, per-symbol evaluate, manual freeze, manual release,
  history, sweep-expired) return the documented shapes.
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.main import app
from app.core.config import AppSettings
from app.data_quality.data_sufficiency_gate import (
    DataSufficiencyGate,
    SufficiencyInputs,
)
from app.database.base import Base
from app.database.connection import get_db_session
from app.database.models import DailyPrice
from app.decision.decision_labels import (
    NO_TRADE,
    OPTION_DATA_NOT_AVAILABLE,
    READY_TO_RESEARCH_STOCK_ONLY,
)
from app.decision.decision_service import DecisionService
from app.decision.final_decision_builder import build_final_decision
from app.decision.stock_thesis_decision import StockThesisInputs
from app.earnings.earnings_models import EarningsRiskSnapshot
from app.hard_filter.hard_filter_gate import (
    EarningsContext,
    HardFilterGate,
    OptionContext,
    RegimeContext,
    StockContext,
)
from app.hard_filter.hard_filter_service import HardFilterService
from app.market_regime.market_regime_models import MarketRegimeSnapshot
from app.options.manual_option_input_service import ManualOptionInputService
from app.options.manual_option_models import ManualOptionSnapshotRecord
from app.profiles.default_profiles import get_balanced_research_default
from app.quant.stock_setup_models import StockSetup
from app.rejection.rejection_classifier import classify_rejection
from app.rejection.rejection_models import RejectedCandidate
from app.rejection.rejection_service import RejectionService
from app.risk_control.do_not_touch_categories import (
    DEFAULT_REPEATED_REJECTIONS_THRESHOLD,
    EVENT_EXPIRED,
    EVENT_FROZEN,
    EVENT_RELEASED,
    EVENT_RENEWED,
    FREEZE_CATEGORY_EARNINGS_BEFORE_EXPIRATION,
    FREEZE_CATEGORY_EXTREME_OPTION_LIQUIDITY_RISK,
    FREEZE_CATEGORY_EXTREME_OPTION_VOLATILITY,
    FREEZE_CATEGORY_MANUAL,
    FREEZE_CATEGORY_REPEATED_REJECTIONS,
    RELEASE_KIND_EVENT,
    RELEASE_KIND_MANUAL,
    RELEASE_KIND_TIME,
    SEVERITY_HARD_FREEZE,
    SEVERITY_SOFT_FREEZE,
)
from app.risk_control.do_not_touch_classifier import (
    DECISION_FREEZE,
    DECISION_NO_FREEZE,
    classify_do_not_touch,
)
from app.risk_control.do_not_touch_explainer import explain_freeze
from app.risk_control.do_not_touch_models import (
    DoNotTouchHistory,
    DoNotTouchItem,
)
from app.risk_control.do_not_touch_service import DoNotTouchService
from app.risk_control.freeze_expiration_monitor import FreezeExpirationMonitor
from app.risk_control.release_condition_builder import build_release_condition
from app.risk_control.temporary_freeze_manager import TemporaryFreezeManager

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


def _ok_sufficiency_inputs(**overrides) -> SufficiencyInputs:
    defaults = dict(
        symbol="AMD",
        price_rows=_price_rows(60),
        stock_setup_status="SUFFICIENT",
        option_rows=None,
        news_rows=[
            {
                "source": "Yahoo Finance",
                "title": "AMD update",
                "event_time": datetime(2026, 5, 10, tzinfo=timezone.utc),
            }
        ],
        iv_history_rows=[
            {"snapshot_date": date(2026, 5, 1), "atm_iv_30d": 0.5} for _ in range(40)
        ],
        earnings_rows=[{"symbol": "AMD"}],
        memory_rows=[{"id": 1}],
    )
    defaults.update(overrides)
    return SufficiencyInputs(**defaults)


def _strong_stock(**overrides) -> StockContext:
    base = dict(
        symbol="AMD",
        snapshot_date=date(2026, 5, 15),
        direction="LONG",
        current_close=100.0,
        nearest_support=95.0,
        nearest_resistance=120.0,
        sma_50=98.0,
        atr_14=2.0,
        stock_risk_reward=4.0,
        target_price=120.0,
    )
    base.update(overrides)
    return StockContext(**base)


def _good_option(**overrides) -> OptionContext:
    base = dict(
        option_type="CALL",
        strike=100.0,
        dte=60,
        expiration_date=date(2026, 7, 15),
        bid=4.9,
        ask=5.1,
        last_price=5.0,
        open_interest=2000,
        implied_volatility=0.50,
        underlying_price=100.0,
    )
    base.update(overrides)
    return OptionContext(**base)


def _build_decision_and_rejection(
    *,
    sufficiency_inputs: SufficiencyInputs,
    stock: StockContext,
    option: OptionContext | None = None,
    regime: RegimeContext | None = None,
    earnings: EarningsContext | None = None,
    option_data_requested: bool = False,
    profile=None,
    thesis_inputs: StockThesisInputs | None = None,
):
    profile = profile or get_balanced_research_default()
    suff = DataSufficiencyGate().evaluate_inputs(sufficiency_inputs, profile=profile)
    hf = HardFilterGate(settings=AppSettings()).evaluate(
        stock=stock,
        option=option,
        regime=regime,
        earnings=earnings,
        profile=profile,
    )
    decision = build_final_decision(
        symbol=stock.symbol,
        snapshot_date=stock.snapshot_date,
        sufficiency=suff,
        hard_filter=hf,
        thesis_inputs=thesis_inputs
        or StockThesisInputs(
            direction=stock.direction,
            current_close=stock.current_close,
            entry_zone_low=95.0,
            entry_zone_high=102.0,
        ),
        option_data_requested=option_data_requested,
        profile=profile,
    )
    rejection = classify_rejection(
        decision,
        profile_minimum_risk_reward=float(profile.minimum_risk_reward),
    )
    return decision, rejection


# ---------------------------------------------------------------------------
# Classifier — invariants
# ---------------------------------------------------------------------------


def test_invariant_missing_option_data_never_freezes() -> None:
    """The defining Phase 24 invariant #1."""
    decision, rejection = _build_decision_and_rejection(
        sufficiency_inputs=_ok_sufficiency_inputs(),
        stock=_strong_stock(),
        option=None,
        regime=RegimeContext(regime_label="RISK_ON"),
        earnings=EarningsContext(risk_label="NO_EARNINGS_NEAR"),
        option_data_requested=True,
    )
    assert decision.final_label == OPTION_DATA_NOT_AVAILABLE
    rec = classify_do_not_touch(decision=decision, rejection=rejection)
    assert rec.decision == DECISION_NO_FREEZE
    assert rec.category is None


def test_invariant_extreme_iv_pasted_option_freezes() -> None:
    """The defining Phase 24 invariant #2."""
    bad = OptionContext(**{**_good_option().__dict__, "implied_volatility": 0.95})
    decision, rejection = _build_decision_and_rejection(
        sufficiency_inputs=_ok_sufficiency_inputs(),
        stock=_strong_stock(),
        option=bad,
        regime=RegimeContext(regime_label="RISK_ON"),
        earnings=EarningsContext(risk_label="NO_EARNINGS_NEAR"),
        option_data_requested=True,
    )
    rec = classify_do_not_touch(decision=decision, rejection=rejection)
    assert rec.decision == DECISION_FREEZE
    assert rec.category == FREEZE_CATEGORY_EXTREME_OPTION_VOLATILITY
    assert rec.severity == SEVERITY_HARD_FREEZE


def test_extreme_liquidity_pasted_option_freezes_soft() -> None:
    bad = OptionContext(
        **{**_good_option().__dict__, "bid": 4.0, "ask": 6.0, "open_interest": 5}
    )
    decision, rejection = _build_decision_and_rejection(
        sufficiency_inputs=_ok_sufficiency_inputs(),
        stock=_strong_stock(),
        option=bad,
        regime=RegimeContext(regime_label="RISK_ON"),
        earnings=EarningsContext(risk_label="NO_EARNINGS_NEAR"),
        option_data_requested=True,
    )
    rec = classify_do_not_touch(decision=decision, rejection=rejection)
    assert rec.decision == DECISION_FREEZE
    assert rec.category == FREEZE_CATEGORY_EXTREME_OPTION_LIQUIDITY_RISK
    assert rec.severity == SEVERITY_SOFT_FREEZE


def test_earnings_before_expiration_freezes_hard() -> None:
    decision, rejection = _build_decision_and_rejection(
        sufficiency_inputs=_ok_sufficiency_inputs(),
        stock=_strong_stock(),
        regime=RegimeContext(regime_label="RISK_ON"),
        earnings=EarningsContext(
            risk_label="EARNINGS_BEFORE_EXPIRATION",
            earnings_within_window=True,
            earnings_before_expiration="TRUE",
            earnings_risk_window_days=7,
            days_to_earnings=2,
        ),
    )
    rec = classify_do_not_touch(decision=decision, rejection=rejection)
    assert rec.decision == DECISION_FREEZE
    assert rec.category == FREEZE_CATEGORY_EARNINGS_BEFORE_EXPIRATION
    assert rec.severity == SEVERITY_HARD_FREEZE


def test_healthy_candidate_does_not_freeze() -> None:
    decision, rejection = _build_decision_and_rejection(
        sufficiency_inputs=_ok_sufficiency_inputs(),
        stock=_strong_stock(),
        regime=RegimeContext(regime_label="RISK_ON"),
        earnings=EarningsContext(risk_label="NO_EARNINGS_NEAR"),
    )
    assert decision.final_label == READY_TO_RESEARCH_STOCK_ONLY
    rec = classify_do_not_touch(decision=decision, rejection=rejection)
    assert rec.decision == DECISION_NO_FREEZE


def test_single_no_trade_does_not_freeze_without_history() -> None:
    decision, rejection = _build_decision_and_rejection(
        sufficiency_inputs=_ok_sufficiency_inputs(),
        stock=_strong_stock(stock_risk_reward=1.0),
        regime=RegimeContext(regime_label="RISK_ON"),
        earnings=EarningsContext(risk_label="NO_EARNINGS_NEAR"),
    )
    assert decision.final_label == NO_TRADE
    rec = classify_do_not_touch(decision=decision, rejection=rejection)
    # Without DB or repeated history, NO_TRADE alone is not enough.
    assert rec.decision == DECISION_NO_FREEZE


# ---------------------------------------------------------------------------
# Release condition builder
# ---------------------------------------------------------------------------


def test_release_condition_event_based_for_earnings() -> None:
    cond = build_release_condition(
        category=FREEZE_CATEGORY_EARNINGS_BEFORE_EXPIRATION,
        now=datetime(2026, 5, 15, tzinfo=timezone.utc),
        earnings_datetime_utc=datetime(2026, 5, 20, tzinfo=timezone.utc),
    )
    assert cond.kind == RELEASE_KIND_EVENT
    assert cond.expires_at == datetime(2026, 5, 21, tzinfo=timezone.utc)


def test_release_condition_time_based_for_iv() -> None:
    now = datetime(2026, 5, 15, tzinfo=timezone.utc)
    cond = build_release_condition(
        category=FREEZE_CATEGORY_EXTREME_OPTION_VOLATILITY,
        now=now,
    )
    assert cond.kind == RELEASE_KIND_TIME
    assert cond.expires_at is not None
    assert cond.expires_at > now


def test_release_condition_manual_is_indefinite_by_default() -> None:
    cond = build_release_condition(category=FREEZE_CATEGORY_MANUAL)
    assert cond.kind == RELEASE_KIND_MANUAL
    assert cond.expires_at is None


# ---------------------------------------------------------------------------
# Explainer
# ---------------------------------------------------------------------------


def test_explainer_returns_user_actions_per_category() -> None:
    for cat in (
        FREEZE_CATEGORY_EARNINGS_BEFORE_EXPIRATION,
        FREEZE_CATEGORY_EXTREME_OPTION_VOLATILITY,
        FREEZE_CATEGORY_EXTREME_OPTION_LIQUIDITY_RISK,
        FREEZE_CATEGORY_REPEATED_REJECTIONS,
        FREEZE_CATEGORY_MANUAL,
    ):
        explanation = explain_freeze(category=cat, severity=SEVERITY_HARD_FREEZE)
        assert explanation.category == cat
        assert explanation.headline
        assert explanation.body
        assert explanation.user_actions


# ---------------------------------------------------------------------------
# DB-path: freeze manager + expiration monitor
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


def _seed_prices(symbol: str, n: int) -> None:
    session = _TestSession()
    try:
        for _i, row in enumerate(_price_rows(n)):
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
        risk_reason="No earnings near.",
        data_sufficiency_status="SUFFICIENT",
    )
    defaults.update(overrides)
    try:
        session.add(EarningsRiskSnapshot(**defaults))
        session.commit()
    finally:
        session.close()


def test_freeze_manager_inserts_item_and_history() -> None:
    manager = TemporaryFreezeManager()
    cond = build_release_condition(
        category=FREEZE_CATEGORY_EXTREME_OPTION_VOLATILITY,
        now=datetime(2026, 5, 15, tzinfo=timezone.utc),
    )
    session = _TestSession()
    try:
        result = manager.freeze(
            session,
            symbol="amd",
            category=FREEZE_CATEGORY_EXTREME_OPTION_VOLATILITY,
            severity=SEVERITY_HARD_FREEZE,
            release_condition=cond,
            reason_summary="IV too high",
        )
        item_count = session.query(DoNotTouchItem).count()
        history_count = session.query(DoNotTouchHistory).count()
        item = session.query(DoNotTouchItem).first()
    finally:
        session.close()
    assert result.event_type == EVENT_FROZEN
    assert item_count == 1
    assert history_count == 1
    assert item.symbol == "AMD"
    assert item.freeze_category == FREEZE_CATEGORY_EXTREME_OPTION_VOLATILITY


def test_freeze_manager_idempotent_same_category() -> None:
    manager = TemporaryFreezeManager()
    cond = build_release_condition(
        category=FREEZE_CATEGORY_EXTREME_OPTION_VOLATILITY
    )
    session = _TestSession()
    try:
        manager.freeze(
            session,
            symbol="AMD",
            category=FREEZE_CATEGORY_EXTREME_OPTION_VOLATILITY,
            severity=SEVERITY_HARD_FREEZE,
            release_condition=cond,
            reason_summary="IV too high",
        )
        second = manager.freeze(
            session,
            symbol="AMD",
            category=FREEZE_CATEGORY_EXTREME_OPTION_VOLATILITY,
            severity=SEVERITY_HARD_FREEZE,
            release_condition=cond,
            reason_summary="IV too high",
        )
        item_count = session.query(DoNotTouchItem).count()
        history_count = session.query(DoNotTouchHistory).count()
    finally:
        session.close()
    assert second.event_type is None  # no-op
    assert item_count == 1
    assert history_count == 1


def test_freeze_manager_upgrades_severity() -> None:
    manager = TemporaryFreezeManager()
    cond_soft = build_release_condition(
        category=FREEZE_CATEGORY_REPEATED_REJECTIONS
    )
    cond_hard = build_release_condition(
        category=FREEZE_CATEGORY_EXTREME_OPTION_VOLATILITY
    )
    session = _TestSession()
    try:
        manager.freeze(
            session,
            symbol="AMD",
            category=FREEZE_CATEGORY_REPEATED_REJECTIONS,
            severity=SEVERITY_SOFT_FREEZE,
            release_condition=cond_soft,
            reason_summary="soft",
        )
        upgrade = manager.freeze(
            session,
            symbol="AMD",
            category=FREEZE_CATEGORY_EXTREME_OPTION_VOLATILITY,
            severity=SEVERITY_HARD_FREEZE,
            release_condition=cond_hard,
            reason_summary="hard",
        )
        item = session.query(DoNotTouchItem).filter_by(symbol="AMD").one()
        history_count = session.query(DoNotTouchHistory).count()
    finally:
        session.close()
    assert upgrade.event_type == EVENT_RENEWED
    assert item.freeze_severity == SEVERITY_HARD_FREEZE
    assert item.freeze_category == FREEZE_CATEGORY_EXTREME_OPTION_VOLATILITY
    assert history_count == 2  # FROZEN + RENEWED


def test_freeze_manager_release_removes_item_and_logs_history() -> None:
    manager = TemporaryFreezeManager()
    cond = build_release_condition(category=FREEZE_CATEGORY_MANUAL)
    session = _TestSession()
    try:
        manager.freeze(
            session,
            symbol="AMD",
            category=FREEZE_CATEGORY_MANUAL,
            severity=SEVERITY_HARD_FREEZE,
            release_condition=cond,
            reason_summary="manual",
        )
        manager.release(session, symbol="AMD", release_reason="done")
        item_count = session.query(DoNotTouchItem).count()
        events = [r.event_type for r in session.query(DoNotTouchHistory).all()]
    finally:
        session.close()
    assert item_count == 0
    assert EVENT_FROZEN in events
    assert EVENT_RELEASED in events


def test_freeze_manager_release_is_idempotent_no_active() -> None:
    manager = TemporaryFreezeManager()
    session = _TestSession()
    try:
        result = manager.release(session, symbol="AMD", release_reason="x")
        history_count = session.query(DoNotTouchHistory).count()
    finally:
        session.close()
    assert result.event_type is None
    assert history_count == 0


def test_freeze_expiration_monitor_releases_expired() -> None:
    manager = TemporaryFreezeManager()
    past = datetime.now(timezone.utc) - timedelta(days=1)
    cond_past = build_release_condition(
        category=FREEZE_CATEGORY_EXTREME_OPTION_VOLATILITY,
        override_expires_at=past,
    )
    future = datetime.now(timezone.utc) + timedelta(days=30)
    cond_future = build_release_condition(
        category=FREEZE_CATEGORY_EXTREME_OPTION_VOLATILITY,
        override_expires_at=future,
    )
    session = _TestSession()
    try:
        manager.freeze(
            session,
            symbol="EXP",
            category=FREEZE_CATEGORY_EXTREME_OPTION_VOLATILITY,
            severity=SEVERITY_HARD_FREEZE,
            release_condition=cond_past,
            reason_summary="expired",
        )
        manager.freeze(
            session,
            symbol="LIVE",
            category=FREEZE_CATEGORY_EXTREME_OPTION_VOLATILITY,
            severity=SEVERITY_HARD_FREEZE,
            release_condition=cond_future,
            reason_summary="still live",
        )
        monitor = FreezeExpirationMonitor(freeze_manager=manager)
        result = monitor.sweep_expired(session)
        active_symbols = {
            r.symbol for r in session.query(DoNotTouchItem).all()
        }
        events = [
            r.event_type
            for r in session.query(DoNotTouchHistory)
            .order_by(DoNotTouchHistory.id.asc())
            .all()
        ]
    finally:
        session.close()
    assert result.swept_count == 1
    assert "EXP" in result.released_symbols
    assert "LIVE" not in result.released_symbols
    assert active_symbols == {"LIVE"}
    assert EVENT_EXPIRED in events


# ---------------------------------------------------------------------------
# DoNotTouchService end-to-end
# ---------------------------------------------------------------------------


def test_service_does_not_freeze_when_only_option_data_missing() -> None:
    """The defining Phase 24 invariant at the service / DB layer."""
    _seed_prices("AMD", 60)
    _seed_setup("AMD")
    _seed_regime("RISK_ON")
    _seed_earnings("AMD")

    session = _TestSession()
    try:
        evaluation = DoNotTouchService().evaluate_symbol(
            session,
            "AMD",
            option_data_requested=True,
            persist=True,
        )
        active_count = session.query(DoNotTouchItem).count()
    finally:
        session.close()
    assert evaluation.recommendation.decision == DECISION_NO_FREEZE
    assert active_count == 0


def test_service_freezes_on_extreme_iv_pasted_option() -> None:
    _seed_prices("AMD", 60)
    _seed_setup("AMD")
    _seed_regime("RISK_ON")
    _seed_earnings("AMD")

    # Inject a fake manual option service with an extreme-IV contract.
    fake = ManualOptionSnapshotRecord(
        id=1, raw_text="x", symbol="AMD", source_name="m",
        underlying_price=100.0, expiration_date=date(2026, 7, 15),
        option_type="CALL", strike=100.0,
        bid=4.9, ask=5.1, last_price=5.0, volume=500, open_interest=2000,
        implied_volatility=0.95,  # extreme IV
        delta=0.5, gamma=None, theta=None, vega=None, rho=None,
        dte=60, mid_price=5.0, spread_percent=4.0, contract_cost=500.0,
        breakeven=105.0, breakeven_distance=5.0, breakeven_distance_percent=5.0,
        parser_confidence="HIGH", missing_fields=[], parsed_fields={},
        data_quality_status="USABLE_OPTION_DATA", ai_status="NOT_ANALYZED",
        ai_summary=None, ai_analysis_json=None,
        created_at=datetime(2026, 5, 15, tzinfo=timezone.utc),
    )

    class _FakeManualService(ManualOptionInputService):
        def __init__(self):
            pass

        def get_manual_snapshot_by_id(self, db, snapshot_id):
            return fake if snapshot_id == 1 else None

    settings = AppSettings()
    manual_service = _FakeManualService()
    hf = HardFilterService(settings=settings)
    decision_service = DecisionService(
        settings=settings,
        hard_filter_service=hf,
        manual_option_service=manual_service,
    )
    from app.action.action_service import ActionSuggestionService

    action_service = ActionSuggestionService(
        settings=settings,
        decision_service=decision_service,
        manual_option_service=manual_service,
    )
    rejection_service = RejectionService(
        settings=settings, action_service=action_service
    )
    dnt_service = DoNotTouchService(
        settings=settings, rejection_service=rejection_service
    )

    session = _TestSession()
    try:
        evaluation = dnt_service.evaluate_symbol(
            session,
            "AMD",
            manual_option_snapshot_id=1,
            option_data_requested=True,
            persist=True,
        )
        item = session.query(DoNotTouchItem).filter_by(symbol="AMD").one()
        history = session.query(DoNotTouchHistory).all()
    finally:
        session.close()

    assert evaluation.recommendation.decision == DECISION_FREEZE
    assert evaluation.recommendation.category == FREEZE_CATEGORY_EXTREME_OPTION_VOLATILITY
    assert item.freeze_category == FREEZE_CATEGORY_EXTREME_OPTION_VOLATILITY
    assert len(history) == 1
    assert history[0].event_type == EVENT_FROZEN
    assert evaluation.explanation is not None
    body_lower = evaluation.explanation.body.lower()
    assert "iv" in body_lower
    assert "volatility" in body_lower


def test_service_repeated_rejections_trigger_freeze() -> None:
    """Seed enough rejected_candidates history to trip the threshold."""
    _seed_prices("AMD", 60)
    _seed_setup("AMD", stock_risk_reward=1.0)  # weak R:R -> NO_TRADE
    _seed_regime("RISK_ON")
    _seed_earnings("AMD")

    session = _TestSession()
    try:
        # Seed `threshold` historical HARD_STOCK_REJECTION rows for AMD.
        from app.rejection.rejection_categories import (
            CATEGORY_HARD_STOCK_REJECTION,
            SEVERITY_HARD_REJECT,
        )

        for i in range(DEFAULT_REPEATED_REJECTIONS_THRESHOLD):
            session.add(
                RejectedCandidate(
                    symbol="AMD",
                    snapshot_date=date(2026, 5, 14 - i),
                    rejection_category=CATEGORY_HARD_STOCK_REJECTION,
                    rejection_severity=SEVERITY_HARD_REJECT,
                    final_action_label="NO_TRADE",
                    lifecycle_state="REJECTED",
                    is_rejected_but_interesting=False,
                    interesting_reasons_json=[],
                    summary="seed",
                )
            )
        session.commit()
        evaluation = DoNotTouchService().evaluate_symbol(
            session, "AMD", persist=True
        )
        active = session.query(DoNotTouchItem).filter_by(symbol="AMD").first()
    finally:
        session.close()
    assert evaluation.recommendation.decision == DECISION_FREEZE
    assert evaluation.recommendation.category == FREEZE_CATEGORY_REPEATED_REJECTIONS
    assert active is not None


def test_manual_freeze_and_release_via_service() -> None:
    _seed_prices("AMD", 60)
    _seed_setup("AMD")
    _seed_regime("RISK_ON")
    _seed_earnings("AMD")

    session = _TestSession()
    try:
        service = DoNotTouchService()
        service.manual_freeze(session, symbol="AMD", reason="user paused")
        active = service.is_frozen(session, "AMD")
        service.manual_release(session, symbol="AMD", reason="back to research")
        after = service.is_frozen(session, "AMD")
        history_events = [
            r.event_type for r in session.query(DoNotTouchHistory).all()
        ]
    finally:
        session.close()
    assert active is True
    assert after is False
    assert EVENT_FROZEN in history_events
    assert EVENT_RELEASED in history_events


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


def test_route_list_returns_empty_when_no_freezes() -> None:
    client = TestClient(app)
    response = client.get("/api/do-not-touch")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 0
    assert body["items"] == []


def test_route_manual_freeze_and_release() -> None:
    client = TestClient(app)
    freeze = client.post(
        "/api/do-not-touch/AMD/freeze",
        json={"reason": "manual pause", "severity": "HARD_FREEZE"},
    )
    assert freeze.status_code == 200
    body = freeze.json()
    assert body["active_freeze"]["freeze_category"] == FREEZE_CATEGORY_MANUAL

    listing = client.get("/api/do-not-touch").json()
    assert listing["count"] == 1

    release = client.post(
        "/api/do-not-touch/AMD/release", json={"reason": "release"}
    )
    assert release.status_code == 200
    assert release.json()["operation"]["event_type"] == EVENT_RELEASED

    listing_after = client.get("/api/do-not-touch").json()
    assert listing_after["count"] == 0


def test_route_evaluate_dry_run_does_not_persist() -> None:
    _seed_prices("AMD", 60)
    _seed_setup("AMD")
    _seed_regime("RISK_ON")
    _seed_earnings("AMD")

    client = TestClient(app)
    response = client.get(
        "/api/do-not-touch/AMD",
        params={"option_data_requested": "true", "persist": "false"},
    )
    assert response.status_code == 200
    body = response.json()
    # Missing-option invariant: recommendation is NO_FREEZE.
    assert body["evaluation"]["recommendation"]["decision"] == DECISION_NO_FREEZE
    assert body["active_freeze"] is None


def test_route_sweep_expired_runs_cleanly() -> None:
    client = TestClient(app)
    response = client.post("/api/do-not-touch/sweep-expired")
    assert response.status_code == 200
    assert response.json()["result"]["swept_count"] == 0


def test_route_history_returns_audit_trail() -> None:
    client = TestClient(app)
    client.post(
        "/api/do-not-touch/AMD/freeze",
        json={"reason": "manual pause", "severity": "HARD_FREEZE"},
    )
    client.post(
        "/api/do-not-touch/AMD/release", json={"reason": "release"}
    )
    response = client.get("/api/do-not-touch/history/AMD")
    assert response.status_code == 200
    body = response.json()
    events = [row["event_type"] for row in body["history"]]
    assert EVENT_FROZEN in events
    assert EVENT_RELEASED in events


def test_route_rejects_empty_symbol() -> None:
    client = TestClient(app)
    response = client.get("/api/do-not-touch/%20")
    assert response.status_code == 400


def test_route_manual_freeze_rejects_bad_severity() -> None:
    client = TestClient(app)
    response = client.post(
        "/api/do-not-touch/AMD/freeze",
        json={"reason": "x", "severity": "WHATEVER"},
    )
    assert response.status_code == 400
