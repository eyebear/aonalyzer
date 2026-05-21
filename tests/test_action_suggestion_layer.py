"""Phase 22, step 22.14 — focused tests for the action suggestion layer.

Covers:

* every final action label mapping to the right lifecycle state;
* the package formatter shape (all 19 documented fields);
* conditional generation of option_contract_criteria + manual_option_input_needed;
* entry / invalidation / upgrade / downgrade / watch / next_review builders;
* action_items merge sufficiency fixes + manual-option prompt + lifecycle items;
* DB service persistence + route shape;
* Phase 19/20/21 regression: missing options still produce a clean
  stock-only package.
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
    LIFECYCLE_INSUFFICIENT_DATA,
    LIFECYCLE_READY_FOR_RESEARCH,
    LIFECYCLE_REJECTED,
    LIFECYCLE_WAITING_FOR_ENTRY,
    LIFECYCLE_WATCHING,
    lifecycle_state_for,
)
from app.action.action_models import ActionSuggestion
from app.action.action_package_formatter import (
    ActionFormatterInputs,
    format_action_package,
)
from app.action.action_service import ActionSuggestionService
from app.action.entry_condition_builder import (
    STATE_NOT_APPLICABLE,
    STATE_READY,
    STATE_WAIT,
    StockSetupSnapshot,
    build_entry_condition,
)
from app.action.invalidation_condition_builder import build_invalidation_condition
from app.action.next_review_trigger_builder import (
    CADENCE_DAILY,
    CADENCE_EVENT,
    CADENCE_MARKET_DATA,
    build_next_review_trigger,
)
from app.action.option_contract_criteria_builder import (
    build_option_contract_criteria,
    is_option_relevant,
)
from app.action.suggested_action_summary import build_suggested_action_summary
from app.action.watch_condition_builder import build_watch_condition
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
    INSUFFICIENT_PRICE_HISTORY,
    NO_TRADE,
    OPTION_DATA_NOT_AVAILABLE,
    READY_TO_RESEARCH_STOCK_ONLY,
    READY_TO_RESEARCH_WITH_OPTION,
    STOCK_OK_OPTION_BAD,
    WAIT_FOR_ENTRY_STOCK_ONLY,
    WATCH_STOCK_ONLY,
)
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
from app.market_regime.market_regime_models import MarketRegimeSnapshot
from app.profiles.default_profiles import get_balanced_research_default
from app.quant.stock_setup_models import StockSetup


# ---------------------------------------------------------------------------
# Helpers reused from Phase 21 tests
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


def _setup_snapshot() -> StockSetupSnapshot:
    return StockSetupSnapshot(
        direction="LONG",
        current_close=100.0,
        entry_zone_low=95.0,
        entry_zone_high=102.0,
        nearest_support=95.0,
        nearest_resistance=120.0,
    )


def _build_package(
    *,
    sufficiency_inputs: SufficiencyInputs,
    stock: StockContext,
    option: OptionContext | None = None,
    regime: RegimeContext | None = None,
    earnings: EarningsContext | None = None,
    option_data_requested: bool = False,
    option_already_supplied: bool = False,
    profile=None,
    thesis_inputs: StockThesisInputs | None = None,
    formatter_inputs: ActionFormatterInputs | None = None,
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
    inputs = formatter_inputs or ActionFormatterInputs(
        setup=_setup_snapshot(),
        stop_price=93.0,
        days_to_earnings=78,
        next_earnings_iso="2026-08-01T00:00:00+00:00",
        option_already_supplied=option_already_supplied,
        option_data_requested=option_data_requested,
    )
    return decision, format_action_package(
        decision=decision,
        inputs=inputs,
        profile=profile,
        settings=AppSettings(),
    )


# ---------------------------------------------------------------------------
# Lifecycle-state mapping
# ---------------------------------------------------------------------------


def test_lifecycle_state_for_each_final_label() -> None:
    assert lifecycle_state_for(READY_TO_RESEARCH_STOCK_ONLY) == LIFECYCLE_READY_FOR_RESEARCH
    assert lifecycle_state_for(READY_TO_RESEARCH_WITH_OPTION) == LIFECYCLE_READY_FOR_RESEARCH
    assert lifecycle_state_for(STOCK_OK_OPTION_BAD) == LIFECYCLE_READY_FOR_RESEARCH
    assert lifecycle_state_for(WATCH_STOCK_ONLY) == LIFECYCLE_WATCHING
    assert lifecycle_state_for(WAIT_FOR_ENTRY_STOCK_ONLY) == LIFECYCLE_WAITING_FOR_ENTRY
    assert lifecycle_state_for(OPTION_DATA_NOT_AVAILABLE) == LIFECYCLE_AWAITING_OPTION_DATA
    assert lifecycle_state_for(NO_TRADE) == LIFECYCLE_REJECTED
    assert lifecycle_state_for(INSUFFICIENT_PRICE_HISTORY) == LIFECYCLE_INSUFFICIENT_DATA


# ---------------------------------------------------------------------------
# Package formatter end-to-end coverage
# ---------------------------------------------------------------------------


def test_package_for_ready_to_research_stock_only() -> None:
    _, pkg = _build_package(
        sufficiency_inputs=_ok_sufficiency_inputs(),
        stock=_strong_stock(),
        regime=RegimeContext(regime_label="RISK_ON"),
        earnings=EarningsContext(risk_label="NO_EARNINGS_NEAR"),
    )
    assert pkg.final_action_label == READY_TO_RESEARCH_STOCK_ONLY
    assert pkg.lifecycle_state == LIFECYCLE_READY_FOR_RESEARCH
    assert pkg.entry_condition.state == STATE_READY
    assert pkg.option_contract_criteria is None  # not requested, not supplied
    assert pkg.manual_option_input_needed is False


def test_package_for_ready_with_option() -> None:
    _, pkg = _build_package(
        sufficiency_inputs=_ok_sufficiency_inputs(),
        stock=_strong_stock(),
        option=_good_option(),
        regime=RegimeContext(regime_label="RISK_ON"),
        earnings=EarningsContext(risk_label="NO_EARNINGS_NEAR"),
        option_data_requested=True,
        option_already_supplied=True,
    )
    assert pkg.final_action_label == READY_TO_RESEARCH_WITH_OPTION
    assert pkg.option_contract_criteria is not None
    assert pkg.option_contract_criteria.direction_hint == "CALL"
    assert pkg.manual_option_input_needed is False


def test_package_for_stock_ok_option_bad_requests_repaste() -> None:
    bad = OptionContext(**{**_good_option().__dict__, "bid": 4.0, "ask": 6.0})
    _, pkg = _build_package(
        sufficiency_inputs=_ok_sufficiency_inputs(),
        stock=_strong_stock(),
        option=bad,
        regime=RegimeContext(regime_label="RISK_ON"),
        earnings=EarningsContext(risk_label="NO_EARNINGS_NEAR"),
        option_data_requested=True,
        option_already_supplied=True,
    )
    assert pkg.final_action_label == STOCK_OK_OPTION_BAD
    assert pkg.lifecycle_state == LIFECYCLE_READY_FOR_RESEARCH
    assert pkg.manual_option_input_needed is True
    actions = {a["action"] for a in pkg.action_items}
    assert "REPASTE_MANUAL_OPTION" in actions


def test_package_for_option_data_not_available_prompts_paste() -> None:
    _, pkg = _build_package(
        sufficiency_inputs=_ok_sufficiency_inputs(),
        stock=_strong_stock(),
        option=None,
        regime=RegimeContext(regime_label="RISK_ON"),
        earnings=EarningsContext(risk_label="NO_EARNINGS_NEAR"),
        option_data_requested=True,
    )
    assert pkg.final_action_label == OPTION_DATA_NOT_AVAILABLE
    assert pkg.lifecycle_state == LIFECYCLE_AWAITING_OPTION_DATA
    assert pkg.manual_option_input_needed is True
    assert pkg.option_contract_criteria is not None
    actions = {a["action"] for a in pkg.action_items}
    assert "PASTE_MANUAL_OPTION" in actions


def test_package_for_wait_for_entry() -> None:
    stock = _strong_stock(
        current_close=103.0,
        nearest_support=100.0,
        sma_50=100.0,
        atr_14=2.0,
    )
    formatter_inputs = ActionFormatterInputs(
        setup=StockSetupSnapshot(
            direction="LONG",
            current_close=103.0,
            entry_zone_low=95.0,
            entry_zone_high=102.0,
            nearest_support=100.0,
            nearest_resistance=120.0,
        ),
        stop_price=93.0,
        days_to_earnings=78,
        option_already_supplied=False,
        option_data_requested=False,
    )
    _, pkg = _build_package(
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
        formatter_inputs=formatter_inputs,
    )
    assert pkg.final_action_label == WAIT_FOR_ENTRY_STOCK_ONLY
    assert pkg.entry_condition.state == STATE_WAIT
    assert pkg.lifecycle_state == LIFECYCLE_WAITING_FOR_ENTRY


def test_package_for_watch_stock_only() -> None:
    _, pkg = _build_package(
        sufficiency_inputs=_ok_sufficiency_inputs(),
        stock=_strong_stock(),
        regime=RegimeContext(regime_label="RISK_OFF"),  # opposes LONG -> warning
        earnings=EarningsContext(risk_label="NO_EARNINGS_NEAR"),
    )
    assert pkg.final_action_label == WATCH_STOCK_ONLY
    assert pkg.lifecycle_state == LIFECYCLE_WATCHING
    assert pkg.watch_condition.active is True


def test_package_for_no_trade() -> None:
    _, pkg = _build_package(
        sufficiency_inputs=_ok_sufficiency_inputs(),
        stock=_strong_stock(stock_risk_reward=1.0),
        regime=RegimeContext(regime_label="RISK_ON"),
        earnings=EarningsContext(risk_label="NO_EARNINGS_NEAR"),
    )
    assert pkg.final_action_label == NO_TRADE
    assert pkg.lifecycle_state == LIFECYCLE_REJECTED
    assert pkg.entry_condition.state == STATE_NOT_APPLICABLE


def test_package_for_insufficient_price_history() -> None:
    _, pkg = _build_package(
        sufficiency_inputs=_ok_sufficiency_inputs(price_rows=[]),
        stock=_strong_stock(stock_risk_reward=None),
        regime=RegimeContext(regime_label="RISK_ON"),
        earnings=EarningsContext(risk_label="NO_EARNINGS_NEAR"),
    )
    assert pkg.final_action_label == INSUFFICIENT_PRICE_HISTORY
    assert pkg.lifecycle_state == LIFECYCLE_INSUFFICIENT_DATA
    assert pkg.entry_condition.state == STATE_NOT_APPLICABLE
    # Action items should drive the user to fix the data.
    assert "REFRESH_MARKET_DATA" in {a["action"] for a in pkg.action_items}


# ---------------------------------------------------------------------------
# Phase 19/20/21 invariant: missing options still produce a clean package
# ---------------------------------------------------------------------------


def test_missing_option_yields_stock_only_package_when_not_requested() -> None:
    _, pkg = _build_package(
        sufficiency_inputs=_ok_sufficiency_inputs(),
        stock=_strong_stock(),
        option=None,
        regime=RegimeContext(regime_label="RISK_ON"),
        earnings=EarningsContext(risk_label="NO_EARNINGS_NEAR"),
        option_data_requested=False,
    )
    assert pkg.final_action_label == READY_TO_RESEARCH_STOCK_ONLY
    assert pkg.lifecycle_state == LIFECYCLE_READY_FOR_RESEARCH
    assert pkg.manual_option_input_needed is False
    assert pkg.option_contract_criteria is None


# ---------------------------------------------------------------------------
# Shape of the final package matches the Phase 22 outline
# ---------------------------------------------------------------------------


def test_package_to_dict_has_all_documented_fields() -> None:
    _, pkg = _build_package(
        sufficiency_inputs=_ok_sufficiency_inputs(),
        stock=_strong_stock(),
        regime=RegimeContext(regime_label="RISK_ON"),
        earnings=EarningsContext(risk_label="NO_EARNINGS_NEAR"),
    )
    payload = pkg.to_dict()
    expected = {
        "final_action_label",
        "instrument_scope",
        "lifecycle_state",
        "priority_score",
        "confidence_score",
        "confidence_breakdown",
        "suggested_action_summary",
        "entry_condition",
        "option_expression_status",
        "option_contract_criteria",
        "manual_option_input_needed",
        "invalidation_condition",
        "upgrade_condition",
        "downgrade_condition",
        "watch_condition",
        "next_review_trigger",
        "decision_trace",
        "version_stamp",
        "action_items",
    }
    assert expected.issubset(set(payload.keys()))
    assert payload["symbol"] == "AMD"
    assert payload["suggested_action_summary"]
    assert isinstance(payload["action_items"], list)


# ---------------------------------------------------------------------------
# Builder-level unit tests
# ---------------------------------------------------------------------------


def test_summary_text_uses_symbol() -> None:
    decision, _ = _build_package(
        sufficiency_inputs=_ok_sufficiency_inputs(),
        stock=_strong_stock(),
        regime=RegimeContext(regime_label="RISK_ON"),
        earnings=EarningsContext(risk_label="NO_EARNINGS_NEAR"),
    )
    assert "AMD" in build_suggested_action_summary(decision)


def test_entry_condition_ready_when_inside_zone() -> None:
    cond = build_entry_condition(
        setup=_setup_snapshot(),
        lifecycle_state=LIFECYCLE_READY_FOR_RESEARCH,
    )
    assert cond.state == STATE_READY
    assert cond.entry_zone_low == 95.0
    assert cond.entry_zone_high == 102.0


def test_entry_condition_not_applicable_when_rejected() -> None:
    cond = build_entry_condition(
        setup=_setup_snapshot(),
        lifecycle_state=LIFECYCLE_REJECTED,
    )
    assert cond.state == STATE_NOT_APPLICABLE


def test_option_criteria_omitted_when_irrelevant() -> None:
    assert (
        build_option_contract_criteria(
            profile=get_balanced_research_default(),
            settings=AppSettings(),
            direction="LONG",
            final_label=READY_TO_RESEARCH_STOCK_ONLY,
            option_data_requested=False,
            option_already_supplied=False,
        )
        is None
    )


def test_option_criteria_present_when_requested() -> None:
    crit = build_option_contract_criteria(
        profile=get_balanced_research_default(),
        settings=AppSettings(),
        direction="LONG",
        final_label=READY_TO_RESEARCH_STOCK_ONLY,
        option_data_requested=True,
        option_already_supplied=False,
    )
    assert crit is not None
    assert crit.direction_hint == "CALL"


def test_invalidation_uses_stop_price_when_present() -> None:
    cond = build_invalidation_condition(
        setup=_setup_snapshot(),
        stop_price=93.0,
        nearest_support=95.0,
        nearest_resistance=120.0,
    )
    assert cond.price_invalidation == 93.0
    assert any("93.00" in t for t in cond.triggers)


def test_invalidation_falls_back_to_support_for_long() -> None:
    cond = build_invalidation_condition(
        setup=_setup_snapshot(),
        stop_price=None,
        nearest_support=95.0,
        nearest_resistance=120.0,
    )
    assert cond.price_invalidation == 95.0


def test_next_review_market_data_when_watching() -> None:
    trig = build_next_review_trigger(
        lifecycle_state=LIFECYCLE_WATCHING,
        profile=get_balanced_research_default(),
        days_to_earnings=78,
    )
    assert trig.cadence == CADENCE_MARKET_DATA
    assert trig.earliest_review_after_minutes == 30  # profile default


def test_next_review_event_driven_when_awaiting_option() -> None:
    trig = build_next_review_trigger(
        lifecycle_state=LIFECYCLE_AWAITING_OPTION_DATA,
        profile=get_balanced_research_default(),
    )
    assert trig.cadence == CADENCE_EVENT


def test_next_review_daily_when_rejected() -> None:
    trig = build_next_review_trigger(
        lifecycle_state=LIFECYCLE_REJECTED,
        profile=get_balanced_research_default(),
    )
    assert trig.cadence == CADENCE_DAILY


def test_watch_condition_inactive_when_ready() -> None:
    cond = build_watch_condition(lifecycle_state=LIFECYCLE_READY_FOR_RESEARCH)
    assert cond.active is False


def test_is_option_relevant_logic() -> None:
    assert is_option_relevant(
        READY_TO_RESEARCH_STOCK_ONLY,
        option_data_requested=False,
        option_already_supplied=False,
    ) is False
    assert is_option_relevant(
        READY_TO_RESEARCH_STOCK_ONLY,
        option_data_requested=True,
        option_already_supplied=False,
    ) is True
    assert is_option_relevant(
        STOCK_OK_OPTION_BAD,
        option_data_requested=False,
        option_already_supplied=False,
    ) is True


# ---------------------------------------------------------------------------
# DB-path: ActionSuggestionService + persistence + route
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


def test_service_evaluates_from_db_and_persists() -> None:
    _seed_prices("AMD", 60)
    _seed_setup("AMD")
    _seed_regime("RISK_ON")
    _seed_earnings("AMD")

    session = _TestSession()
    try:
        evaluation = ActionSuggestionService().evaluate_symbol(
            session, "amd", persist=True
        )
    finally:
        session.close()

    assert evaluation.package.symbol == "AMD"
    assert evaluation.package.final_action_label == READY_TO_RESEARCH_STOCK_ONLY
    assert evaluation.record is not None
    assert evaluation.record.lifecycle_state == LIFECYCLE_READY_FOR_RESEARCH


def test_service_persistence_is_idempotent() -> None:
    _seed_prices("AMD", 60)
    _seed_setup("AMD")
    _seed_regime("RISK_ON")
    _seed_earnings("AMD")

    session = _TestSession()
    try:
        service = ActionSuggestionService()
        service.evaluate_symbol(session, "AMD", persist=True)
        service.evaluate_symbol(session, "AMD", persist=True)
        count = session.query(ActionSuggestion).count()
    finally:
        session.close()
    assert count == 1


def test_service_no_persist_when_persist_false() -> None:
    _seed_prices("AMD", 60)
    _seed_setup("AMD")
    _seed_regime("RISK_ON")
    _seed_earnings("AMD")

    session = _TestSession()
    try:
        evaluation = ActionSuggestionService().evaluate_symbol(
            session, "AMD", persist=False
        )
        count = session.query(ActionSuggestion).count()
    finally:
        session.close()
    assert evaluation.record is None
    assert count == 0


def test_service_handles_option_data_requested() -> None:
    _seed_prices("AMD", 60)
    _seed_setup("AMD")
    _seed_regime("RISK_ON")
    _seed_earnings("AMD")

    session = _TestSession()
    try:
        evaluation = ActionSuggestionService().evaluate_symbol(
            session, "AMD", option_data_requested=True, persist=True
        )
    finally:
        session.close()
    assert evaluation.package.final_action_label == OPTION_DATA_NOT_AVAILABLE
    assert evaluation.package.manual_option_input_needed is True
    assert evaluation.record is not None
    assert evaluation.record.manual_option_input_needed is True


def test_route_returns_package_shape() -> None:
    _seed_prices("AMD", 60)
    _seed_setup("AMD")
    _seed_regime("RISK_ON")
    _seed_earnings("AMD")

    client = TestClient(app)
    response = client.get("/api/action-suggestions/AMD")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "OK"
    package = body["package"]
    expected = {
        "final_action_label",
        "instrument_scope",
        "lifecycle_state",
        "priority_score",
        "confidence_score",
        "confidence_breakdown",
        "suggested_action_summary",
        "entry_condition",
        "option_expression_status",
        "option_contract_criteria",
        "manual_option_input_needed",
        "invalidation_condition",
        "upgrade_condition",
        "downgrade_condition",
        "watch_condition",
        "next_review_trigger",
        "decision_trace",
        "version_stamp",
        "action_items",
    }
    assert expected.issubset(set(package.keys()))
    assert body["record_id"] is None


def test_route_persists_and_lists() -> None:
    _seed_prices("AMD", 60)
    _seed_setup("AMD")
    _seed_regime("RISK_ON")
    _seed_earnings("AMD")

    client = TestClient(app)
    response = client.get("/api/action-suggestions/AMD?persist=true")
    assert response.status_code == 200
    body = response.json()
    assert body["record_id"] is not None

    listing = client.get("/api/action-suggestions?symbol=AMD").json()
    assert listing["count"] == 1
    suggestion = listing["suggestions"][0]
    assert suggestion["final_action_label"] == READY_TO_RESEARCH_STOCK_ONLY
    assert suggestion["lifecycle_state"] == LIFECYCLE_READY_FOR_RESEARCH


def test_route_rejects_empty_symbol() -> None:
    client = TestClient(app)
    response = client.get("/api/action-suggestions/%20")
    assert response.status_code == 400


def test_route_returns_404_for_unknown_option_snapshot() -> None:
    _seed_prices("AMD", 60)
    _seed_setup("AMD")
    _seed_regime("RISK_ON")
    _seed_earnings("AMD")

    client = TestClient(app)
    response = client.get(
        "/api/action-suggestions/AMD?manual_option_snapshot_id=9999"
    )
    assert response.status_code == 404
