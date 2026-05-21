"""Phase 21, step 21.15 — focused tests for the decision intelligence layer.

Covers every final action label, plus checklist / priority / confidence /
trace / version-stamp shape, plus the DB service + API route. Reuses the
Phase 19 ``DataSufficiencyGate`` and Phase 20 ``HardFilterGate`` outputs
rather than re-mocking their internals.
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
from app.decision.action_label_classifier import classify_action_label
from app.decision.decision_labels import (
    CHECK_FAIL,
    CHECK_PASS,
    CHECK_WARNING,
    INSUFFICIENT_PRICE_HISTORY,
    NO_TRADE,
    OPTION_DATA_NOT_AVAILABLE,
    OPTION_EXPR_BAD,
    OPTION_EXPR_NOT_EVALUATED,
    OPTION_EXPR_OK,
    READY_TO_RESEARCH_STOCK_ONLY,
    READY_TO_RESEARCH_WITH_OPTION,
    RISK_HIGH,
    RISK_LOW,
    RISK_UNKNOWN,
    SCOPE_OPTION_AVAILABLE,
    SCOPE_OPTION_REJECTED,
    SCOPE_STOCK_ONLY,
    STOCK_OK_OPTION_BAD,
    THESIS_INSUFFICIENT_PRICE_HISTORY,
    THESIS_NO_TRADE,
    THESIS_READY_TO_RESEARCH,
    THESIS_WAIT_FOR_ENTRY,
    THESIS_WATCH,
    WAIT_FOR_ENTRY_STOCK_ONLY,
    WATCH_STOCK_ONLY,
)
from app.decision.decision_models import DecisionSnapshot
from app.decision.decision_service import DecisionService
from app.decision.event_risk_decision import (
    EventRiskInputs,
    decide_event_risk,
)
from app.decision.final_decision_builder import build_final_decision
from app.decision.instrument_scope_classifier import classify_instrument_scope
from app.decision.memory_risk_decision import MemoryRiskInputs, decide_memory_risk
from app.decision.option_expression_decision import decide_option_expression
from app.decision.stock_thesis_decision import (
    StockThesisInputs,
    decide_stock_thesis,
)
from app.decision.version_stamp_builder import (
    DEFAULT_DECISION_ENGINE_VERSION,
    DEFAULT_RULE_VERSION,
    build_version_stamp,
)
from app.earnings.earnings_models import EarningsRiskSnapshot
from app.hard_filter.hard_filter_gate import (
    EarningsContext,
    HardFilterGate,
    OptionContext,
    RegimeContext,
    StockContext,
)
from app.market_regime.market_regime_models import MarketRegimeSnapshot
from app.profiles.default_profiles import get_balanced_research_default
from app.quant.stock_setup_models import StockSetup


# ---------------------------------------------------------------------------
# Helpers — build (sufficiency, hard_filter) pairs for each scenario
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


def _evaluate(
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
    """Build sufficiency + hard-filter outputs and call the decision builder."""
    profile = profile or get_balanced_research_default()
    suff = DataSufficiencyGate().evaluate_inputs(sufficiency_inputs, profile=profile)
    hf = HardFilterGate(settings=AppSettings()).evaluate(
        stock=stock,
        option=option,
        regime=regime,
        earnings=earnings,
        profile=profile,
    )
    return build_final_decision(
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


# ---------------------------------------------------------------------------
# Final-label coverage (the 8 user-facing outcomes)
# ---------------------------------------------------------------------------


def test_ready_to_research_stock_only() -> None:
    decision = _evaluate(
        sufficiency_inputs=_ok_sufficiency_inputs(),
        stock=_strong_stock(),
        regime=RegimeContext(regime_label="RISK_ON"),
        earnings=EarningsContext(risk_label="NO_EARNINGS_NEAR"),
    )
    assert decision.final_label == READY_TO_RESEARCH_STOCK_ONLY
    assert decision.stock_thesis.thesis_label == THESIS_READY_TO_RESEARCH
    assert decision.option_expression.expression_label == OPTION_EXPR_NOT_EVALUATED
    assert decision.instrument_scope.scope == SCOPE_STOCK_ONLY


def test_ready_to_research_with_option() -> None:
    decision = _evaluate(
        sufficiency_inputs=_ok_sufficiency_inputs(),
        stock=_strong_stock(),
        option=_good_option(),
        regime=RegimeContext(regime_label="RISK_ON"),
        earnings=EarningsContext(risk_label="NO_EARNINGS_NEAR"),
        option_data_requested=True,
    )
    assert decision.final_label == READY_TO_RESEARCH_WITH_OPTION
    assert decision.option_expression.expression_label == OPTION_EXPR_OK
    assert decision.instrument_scope.scope == SCOPE_OPTION_AVAILABLE


def test_stock_ok_option_bad() -> None:
    # Bad option: spread too wide
    bad = OptionContext(**{**_good_option().__dict__, "bid": 4.0, "ask": 6.0})
    decision = _evaluate(
        sufficiency_inputs=_ok_sufficiency_inputs(),
        stock=_strong_stock(),
        option=bad,
        regime=RegimeContext(regime_label="RISK_ON"),
        earnings=EarningsContext(risk_label="NO_EARNINGS_NEAR"),
        option_data_requested=True,
    )
    assert decision.final_label == STOCK_OK_OPTION_BAD
    assert decision.option_expression.expression_label == OPTION_EXPR_BAD
    assert decision.instrument_scope.scope == SCOPE_OPTION_REJECTED


def test_option_data_not_available_when_requested() -> None:
    decision = _evaluate(
        sufficiency_inputs=_ok_sufficiency_inputs(),
        stock=_strong_stock(),
        option=None,
        regime=RegimeContext(regime_label="RISK_ON"),
        earnings=EarningsContext(risk_label="NO_EARNINGS_NEAR"),
        option_data_requested=True,
    )
    assert decision.final_label == OPTION_DATA_NOT_AVAILABLE
    assert decision.option_expression.expression_label == OPTION_EXPR_NOT_EVALUATED
    assert decision.instrument_scope.scope == SCOPE_STOCK_ONLY


def test_watch_stock_only_when_hard_filter_warns() -> None:
    decision = _evaluate(
        sufficiency_inputs=_ok_sufficiency_inputs(),
        stock=_strong_stock(),
        regime=RegimeContext(regime_label="RISK_OFF"),  # opposes LONG -> warning
        earnings=EarningsContext(risk_label="NO_EARNINGS_NEAR"),
    )
    assert decision.final_label == WATCH_STOCK_ONLY
    assert decision.stock_thesis.thesis_label == THESIS_WATCH


def test_wait_for_entry_when_outside_entry_zone() -> None:
    # current_close 103 with zone 95-102 -> just outside the entry zone.
    # nearest_support 100 + atr 2 -> ATR extension = 1.5 (below the 3.0 limit)
    # sma_50 100 -> 3% above (below the 15% limit) -- so the hard filter
    # passes and only the entry-zone check trips the wait state.
    stock = _strong_stock(
        current_close=103.0,
        nearest_support=100.0,
        sma_50=100.0,
        atr_14=2.0,
    )
    decision = _evaluate(
        sufficiency_inputs=_ok_sufficiency_inputs(),
        stock=stock,
        regime=RegimeContext(regime_label="RISK_ON"),
        earnings=EarningsContext(risk_label="NO_EARNINGS_NEAR"),
        thesis_inputs=StockThesisInputs(
            direction="LONG",
            current_close=103.0,
            entry_zone_low=95.0,
            entry_zone_high=102.0,
        ),
    )
    assert decision.final_label == WAIT_FOR_ENTRY_STOCK_ONLY
    assert decision.stock_thesis.thesis_label == THESIS_WAIT_FOR_ENTRY


def test_no_trade_when_hard_filter_blocks_stock() -> None:
    # Weak R:R 1.0 -> hard filter blocks
    stock = _strong_stock(stock_risk_reward=1.0)
    decision = _evaluate(
        sufficiency_inputs=_ok_sufficiency_inputs(),
        stock=stock,
        regime=RegimeContext(regime_label="RISK_ON"),
        earnings=EarningsContext(risk_label="NO_EARNINGS_NEAR"),
    )
    assert decision.final_label == NO_TRADE
    assert decision.stock_thesis.thesis_label == THESIS_NO_TRADE


def test_no_trade_when_earnings_before_expiration() -> None:
    decision = _evaluate(
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
    assert decision.final_label == NO_TRADE


def test_insufficient_price_history_blocks_everything() -> None:
    decision = _evaluate(
        sufficiency_inputs=_ok_sufficiency_inputs(price_rows=[]),
        stock=_strong_stock(stock_risk_reward=None),
        regime=RegimeContext(regime_label="RISK_ON"),
        earnings=EarningsContext(risk_label="NO_EARNINGS_NEAR"),
    )
    assert decision.final_label == INSUFFICIENT_PRICE_HISTORY
    assert decision.stock_thesis.thesis_label == THESIS_INSUFFICIENT_PRICE_HISTORY


def test_insufficient_stock_setup_data_blocks_via_phase19_normalization() -> None:
    decision = _evaluate(
        sufficiency_inputs=_ok_sufficiency_inputs(
            stock_setup_status="INSUFFICIENT_SETUP_DATA"
        ),
        stock=_strong_stock(),
        regime=RegimeContext(regime_label="RISK_ON"),
        earnings=EarningsContext(risk_label="NO_EARNINGS_NEAR"),
    )
    assert decision.final_label == NO_TRADE


# ---------------------------------------------------------------------------
# Phase 21 invariant: missing options never produce NO_TRADE on a healthy stock
# ---------------------------------------------------------------------------


def test_missing_option_does_not_cause_no_trade() -> None:
    """Cross-references the Phase 19 + Phase 20 invariant at the Phase 21 layer."""
    decision = _evaluate(
        sufficiency_inputs=_ok_sufficiency_inputs(),
        stock=_strong_stock(),
        option=None,
        regime=RegimeContext(regime_label="RISK_ON"),
        earnings=EarningsContext(risk_label="NO_EARNINGS_NEAR"),
    )
    assert decision.final_label == READY_TO_RESEARCH_STOCK_ONLY
    assert decision.final_label != NO_TRADE


def test_missing_option_with_option_requested_yields_option_data_not_available() -> None:
    decision = _evaluate(
        sufficiency_inputs=_ok_sufficiency_inputs(),
        stock=_strong_stock(),
        option=None,
        regime=RegimeContext(regime_label="RISK_ON"),
        earnings=EarningsContext(risk_label="NO_EARNINGS_NEAR"),
        option_data_requested=True,
    )
    assert decision.final_label == OPTION_DATA_NOT_AVAILABLE
    assert decision.final_label != NO_TRADE


# ---------------------------------------------------------------------------
# Checklist + priority + confidence + trace + version stamp shapes
# ---------------------------------------------------------------------------


def test_checklist_has_expected_statuses() -> None:
    decision = _evaluate(
        sufficiency_inputs=_ok_sufficiency_inputs(),
        stock=_strong_stock(),
        regime=RegimeContext(regime_label="RISK_ON"),
        earnings=EarningsContext(risk_label="NO_EARNINGS_NEAR"),
    )
    statuses = {item.status for item in decision.checklist}
    # Healthy case should have only PASS / WARNING / SKIPPED -- no FAIL.
    assert CHECK_FAIL not in statuses
    names = {item.name for item in decision.checklist}
    assert "price_history_sufficient" in names
    assert "stock_setup_defined" in names
    assert "option_data_available" in names


def test_priority_and_confidence_in_range_when_healthy() -> None:
    decision = _evaluate(
        sufficiency_inputs=_ok_sufficiency_inputs(),
        stock=_strong_stock(),
        regime=RegimeContext(regime_label="RISK_ON"),
        earnings=EarningsContext(risk_label="NO_EARNINGS_NEAR"),
    )
    assert 0.0 <= decision.priority.score <= 100.0
    assert 0.0 <= decision.confidence.score <= 100.0
    # Healthy case should be comfortably above 50.
    assert decision.priority.score > 50
    assert decision.confidence.score > 50


def test_priority_and_confidence_drop_when_blocked() -> None:
    decision = _evaluate(
        sufficiency_inputs=_ok_sufficiency_inputs(),
        stock=_strong_stock(stock_risk_reward=1.0),
        regime=RegimeContext(regime_label="RISK_OFF"),
        earnings=EarningsContext(
            risk_label="EARNINGS_INSIDE_WINDOW",
            earnings_within_window=True,
            earnings_risk_window_days=7,
            days_to_earnings=3,
        ),
    )
    # Hard filter blocks stock -> NO_TRADE -- confidence should be low.
    assert decision.final_label == NO_TRADE
    assert decision.confidence.score < 60


def test_confidence_breakdown_sums_close_to_total() -> None:
    decision = _evaluate(
        sufficiency_inputs=_ok_sufficiency_inputs(),
        stock=_strong_stock(),
        regime=RegimeContext(regime_label="RISK_ON"),
        earnings=EarningsContext(risk_label="NO_EARNINGS_NEAR"),
    )
    breakdown = decision.confidence.breakdown
    total = sum(breakdown.components.values())
    assert abs(total - breakdown.total) < 1e-6


def test_decision_trace_records_each_step() -> None:
    decision = _evaluate(
        sufficiency_inputs=_ok_sufficiency_inputs(),
        stock=_strong_stock(),
        regime=RegimeContext(regime_label="RISK_ON"),
        earnings=EarningsContext(risk_label="NO_EARNINGS_NEAR"),
    )
    steps = [t["step"] for t in decision.trace]
    expected = {
        "data_sufficiency_gate",
        "hard_filter_gate",
        "stock_thesis_decision",
        "option_expression_decision",
        "instrument_scope_classifier",
        "event_risk_decision",
        "memory_risk_decision",
        "action_label_classifier",
    }
    assert expected.issubset(set(steps))


def test_version_stamp_falls_back_without_db() -> None:
    profile = get_balanced_research_default()
    stamp = build_version_stamp(db=None, profile=profile)
    assert stamp.rule_version == DEFAULT_RULE_VERSION
    assert stamp.decision_engine_version == DEFAULT_DECISION_ENGINE_VERSION
    assert stamp.strategy_profile_version == profile.profile_version


def test_final_decision_to_dict_shape_is_stable() -> None:
    decision = _evaluate(
        sufficiency_inputs=_ok_sufficiency_inputs(),
        stock=_strong_stock(),
        regime=RegimeContext(regime_label="RISK_ON"),
        earnings=EarningsContext(risk_label="NO_EARNINGS_NEAR"),
    )
    payload = decision.to_dict()
    expected_top_keys = {
        "symbol",
        "snapshot_date",
        "final_label",
        "rationale",
        "stock_thesis",
        "option_expression",
        "instrument_scope",
        "event_risk",
        "memory_risk",
        "checklist",
        "priority",
        "confidence",
        "trace",
        "version_stamp",
        "sufficiency_decision",
        "hard_filter_decision",
        "profile_name",
        "profile_version",
        "evaluated_at",
    }
    assert expected_top_keys.issubset(set(payload.keys()))


# ---------------------------------------------------------------------------
# Sub-decision unit tests
# ---------------------------------------------------------------------------


def test_event_risk_high_when_earnings_inside_window() -> None:
    risk = decide_event_risk(
        EventRiskInputs(
            earnings_within_window=True,
            earnings_risk_label="EARNINGS_INSIDE_WINDOW",
        )
    )
    assert risk.risk_level == RISK_HIGH


def test_event_risk_low_when_clean() -> None:
    risk = decide_event_risk(
        EventRiskInputs(
            earnings_risk_label="NO_EARNINGS_NEAR",
            iv_state="LOW",
            high_importance_news_count=0,
            news_data_available=True,
        )
    )
    assert risk.risk_level == RISK_LOW


def test_memory_risk_unknown_until_memory_lands() -> None:
    risk = decide_memory_risk(MemoryRiskInputs())
    assert risk.risk_level == RISK_UNKNOWN


def test_option_expression_decision_no_data_is_not_evaluated() -> None:
    # Reuse the Phase 20 hard-filter gate to produce a decision with no
    # option data -> option_decision should be OPTION_NOT_EVALUATED.
    hf = HardFilterGate(settings=AppSettings()).evaluate(
        stock=_strong_stock(), option=None, profile=get_balanced_research_default()
    )
    expr = decide_option_expression(hf)
    assert expr.expression_label == OPTION_EXPR_NOT_EVALUATED


def test_instrument_scope_stock_only_when_no_option() -> None:
    hf = HardFilterGate(settings=AppSettings()).evaluate(
        stock=_strong_stock(), option=None, profile=get_balanced_research_default()
    )
    expr = decide_option_expression(hf)
    scope = classify_instrument_scope(expr, option_data_requested=False)
    assert scope.scope == SCOPE_STOCK_ONLY


# ---------------------------------------------------------------------------
# DB-path: DecisionService + persistence + route
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
        for i, row in enumerate(_price_rows(n)):
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


def test_service_evaluates_from_db_and_persists() -> None:
    _seed_prices("AMD", 60)
    _seed_setup("AMD")
    _seed_regime("RISK_ON")
    _seed_earnings("AMD")

    session = _TestSession()
    try:
        evaluation = DecisionService().evaluate_symbol(session, "amd", persist=True)
    finally:
        session.close()

    assert evaluation.decision.symbol == "AMD"
    assert evaluation.decision.final_label == READY_TO_RESEARCH_STOCK_ONLY
    assert evaluation.record is not None
    assert evaluation.record.final_label == READY_TO_RESEARCH_STOCK_ONLY
    assert evaluation.record.stock_thesis_label == THESIS_READY_TO_RESEARCH


def test_service_persistence_is_idempotent() -> None:
    _seed_prices("AMD", 60)
    _seed_setup("AMD")
    _seed_regime("RISK_ON")
    _seed_earnings("AMD")

    session = _TestSession()
    try:
        service = DecisionService()
        service.evaluate_symbol(session, "AMD", persist=True)
        service.evaluate_symbol(session, "AMD", persist=True)
        count = session.query(DecisionSnapshot).count()
    finally:
        session.close()
    assert count == 1


def test_service_does_not_persist_when_persist_false() -> None:
    _seed_prices("AMD", 60)
    _seed_setup("AMD")
    _seed_regime("RISK_ON")
    _seed_earnings("AMD")

    session = _TestSession()
    try:
        service = DecisionService()
        evaluation = service.evaluate_symbol(session, "AMD", persist=False)
        count = session.query(DecisionSnapshot).count()
    finally:
        session.close()
    assert evaluation.record is None
    assert count == 0


def test_service_yields_no_trade_when_setup_weak() -> None:
    _seed_prices("AMD", 60)
    _seed_setup("AMD", stock_risk_reward=1.0)
    _seed_regime("RISK_ON")
    _seed_earnings("AMD")

    session = _TestSession()
    try:
        evaluation = DecisionService().evaluate_symbol(session, "AMD", persist=True)
    finally:
        session.close()
    assert evaluation.decision.final_label == NO_TRADE


def test_service_yields_insufficient_price_history_with_no_prices() -> None:
    # No prices and no setup seeded.
    session = _TestSession()
    try:
        evaluation = DecisionService().evaluate_symbol(session, "AMD", persist=True)
    finally:
        session.close()
    assert evaluation.decision.final_label == INSUFFICIENT_PRICE_HISTORY


def test_service_uses_version_registry_when_present() -> None:
    from app.database.models import VersionRegistry

    _seed_prices("AMD", 60)
    _seed_setup("AMD")
    _seed_regime("RISK_ON")
    _seed_earnings("AMD")

    session = _TestSession()
    try:
        session.add(
            VersionRegistry(
                version_key="decision_engine_version",
                version_value="decision_engine_0.2_test",
                version_type="DECISION_ENGINE",
                is_active=True,
            )
        )
        session.commit()
        evaluation = DecisionService().evaluate_symbol(session, "AMD", persist=True)
    finally:
        session.close()
    assert (
        evaluation.decision.version_stamp.decision_engine_version
        == "decision_engine_0.2_test"
    )


def test_route_returns_decision_shape() -> None:
    _seed_prices("AMD", 60)
    _seed_setup("AMD")
    _seed_regime("RISK_ON")
    _seed_earnings("AMD")

    client = TestClient(app)
    response = client.get("/api/decisions/AMD")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "OK"
    assert body["decision"]["symbol"] == "AMD"
    assert body["decision"]["final_label"] == READY_TO_RESEARCH_STOCK_ONLY
    assert body["record_id"] is None


def test_route_persists_when_requested() -> None:
    _seed_prices("AMD", 60)
    _seed_setup("AMD")
    _seed_regime("RISK_ON")
    _seed_earnings("AMD")

    client = TestClient(app)
    response = client.get("/api/decisions/AMD?persist=true")
    assert response.status_code == 200
    body = response.json()
    assert body["record_id"] is not None

    listing = client.get("/api/decisions?symbol=AMD").json()
    assert listing["count"] == 1
    assert listing["decisions"][0]["final_label"] == READY_TO_RESEARCH_STOCK_ONLY


def test_route_rejects_empty_symbol() -> None:
    client = TestClient(app)
    response = client.get("/api/decisions/%20")
    assert response.status_code == 400


def test_route_returns_404_for_unknown_option_snapshot() -> None:
    _seed_prices("AMD", 60)
    _seed_setup("AMD")
    _seed_regime("RISK_ON")
    _seed_earnings("AMD")

    client = TestClient(app)
    response = client.get("/api/decisions/AMD?manual_option_snapshot_id=9999")
    assert response.status_code == 404


def test_route_option_data_not_available_when_requested() -> None:
    _seed_prices("AMD", 60)
    _seed_setup("AMD")
    _seed_regime("RISK_ON")
    _seed_earnings("AMD")

    client = TestClient(app)
    response = client.get("/api/decisions/AMD?option_data_requested=true")
    assert response.status_code == 200
    body = response.json()
    assert body["decision"]["final_label"] == OPTION_DATA_NOT_AVAILABLE
