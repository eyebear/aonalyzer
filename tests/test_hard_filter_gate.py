"""Phase 20, step 20.12 — focused tests for the Hard Filter Gate.

These tests exercise the Phase 20 invariants:

* stock hard filters always run, regardless of option presence;
* option hard filters run only when option data exists; otherwise they are
  ``SKIPPED`` and never produce a stock rejection;
* missing option data is never a hard rejection;
* weak stock R:R, price extension, opposing regime, and earnings risk
  produce the correct outcomes;
* hard filter results persist to ``hard_filter_results`` and can be
  re-read via the API route.
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import date, datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.main import app
from app.core.config import AppSettings
from app.database.base import Base
from app.database.connection import get_db_session
from app.earnings.earnings_models import EarningsRiskSnapshot
from app.hard_filter.hard_filter_gate import (
    DECISION_ALLOWED,
    DECISION_BLOCKED,
    EARNINGS_BEFORE_OPTION_EXPIRATION,
    EARNINGS_INSIDE_WINDOW,
    OPTION_DECISION_ALLOWED,
    OPTION_DECISION_BLOCKED,
    OPTION_DECISION_NOT_EVALUATED,
    PRICE_TOO_EXTENDED,
    REGIME_OPPOSES_SETUP,
    WEAK_STOCK_RISK_REWARD,
    EarningsContext,
    HardFilterGate,
    OptionContext,
    RegimeContext,
    StockContext,
)
from app.hard_filter.hard_filter_models import HardFilterResult
from app.hard_filter.hard_filter_service import HardFilterService
from app.market_regime.market_regime_models import MarketRegimeSnapshot
from app.options.iv_analysis import IV_TOO_HIGH
from app.options.option_filters import DTE_TOO_SHORT, LOW_OPEN_INTEREST, SPREAD_TOO_WIDE
from app.options.target_breakeven import TARGET_BELOW_BREAKEVEN
from app.profiles.default_profiles import get_balanced_research_default
from app.quant.stock_setup_models import StockSetup

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _strong_stock() -> StockContext:
    return StockContext(
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


def _good_option() -> OptionContext:
    return OptionContext(
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


# ---------------------------------------------------------------------------
# Stock-only invariants (Phase 20 principle)
# ---------------------------------------------------------------------------


def test_missing_option_data_never_blocks_stock_decision() -> None:
    """The defining Phase 20 invariant."""
    gate = HardFilterGate(settings=AppSettings())
    decision = gate.evaluate(
        stock=_strong_stock(),
        option=None,  # no option data
        regime=RegimeContext(regime_label="RISK_ON", regime_score=2),
        earnings=EarningsContext(risk_label="NO_EARNINGS_NEAR"),
        profile=get_balanced_research_default(),
    )

    assert decision.overall_decision == DECISION_ALLOWED
    assert decision.option_decision == OPTION_DECISION_NOT_EVALUATED
    # All five option filters skipped.
    skipped = set(decision.skipped_filters)
    assert {
        "option_dte",
        "option_target_breakeven",
        "option_spread",
        "option_open_interest",
        "option_iv_extreme",
    }.issubset(skipped)
    assert decision.stock_blocking_labels == []
    assert decision.option_blocking_labels == []


def test_weak_stock_risk_reward_blocks() -> None:
    gate = HardFilterGate(settings=AppSettings())
    stock = _strong_stock()
    stock = StockContext(**{**stock.__dict__, "stock_risk_reward": 1.2})

    decision = gate.evaluate(
        stock=stock,
        profile=get_balanced_research_default(),
    )
    assert decision.overall_decision == DECISION_BLOCKED
    assert WEAK_STOCK_RISK_REWARD in decision.stock_blocking_labels


def test_missing_stock_risk_reward_does_not_block() -> None:
    gate = HardFilterGate(settings=AppSettings())
    stock = StockContext(**{**_strong_stock().__dict__, "stock_risk_reward": None})

    decision = gate.evaluate(
        stock=stock,
        profile=get_balanced_research_default(),
    )
    # Skipped filters never block.
    assert decision.overall_decision == DECISION_ALLOWED
    assert "stock_risk_reward" in decision.skipped_filters


def test_price_extension_blocks_when_too_far_above_support() -> None:
    gate = HardFilterGate(settings=AppSettings())
    # current_close 130, support 95 -> 35 / ATR 2 = 17.5 ATR multiples
    # SMA50 100 -> +30% above SMA50
    stock = StockContext(
        symbol="AMD",
        snapshot_date=date(2026, 5, 15),
        direction="LONG",
        current_close=130.0,
        nearest_support=95.0,
        nearest_resistance=140.0,
        sma_50=100.0,
        atr_14=2.0,
        stock_risk_reward=3.0,
        target_price=140.0,
    )

    decision = gate.evaluate(stock=stock, profile=get_balanced_research_default())
    assert decision.overall_decision == DECISION_BLOCKED
    assert PRICE_TOO_EXTENDED in decision.stock_blocking_labels


def test_price_extension_skipped_for_short_setup() -> None:
    gate = HardFilterGate(settings=AppSettings())
    stock = StockContext(
        symbol="AMD",
        snapshot_date=date(2026, 5, 15),
        direction="SHORT",
        current_close=130.0,
        nearest_support=95.0,
        nearest_resistance=140.0,
        sma_50=100.0,
        atr_14=2.0,
        stock_risk_reward=3.0,
        target_price=80.0,
    )
    decision = gate.evaluate(stock=stock, profile=get_balanced_research_default())
    assert decision.overall_decision == DECISION_ALLOWED
    assert "price_extension" in decision.skipped_filters


def test_market_regime_opposing_setup_warns_not_blocks() -> None:
    """Step 20.4 -- regime is a warning, not a hard fail."""
    gate = HardFilterGate(settings=AppSettings())
    decision = gate.evaluate(
        stock=_strong_stock(),
        regime=RegimeContext(regime_label="RISK_OFF"),
        profile=get_balanced_research_default(),
    )
    assert decision.overall_decision == DECISION_ALLOWED
    assert REGIME_OPPOSES_SETUP in decision.warning_labels
    assert REGIME_OPPOSES_SETUP not in decision.stock_blocking_labels


def test_market_regime_aligned_passes() -> None:
    gate = HardFilterGate(settings=AppSettings())
    decision = gate.evaluate(
        stock=_strong_stock(),
        regime=RegimeContext(regime_label="RISK_ON"),
        profile=get_balanced_research_default(),
    )
    assert REGIME_OPPOSES_SETUP not in decision.warning_labels


def test_earnings_inside_window_is_warning_by_default() -> None:
    gate = HardFilterGate(settings=AppSettings())
    decision = gate.evaluate(
        stock=_strong_stock(),
        earnings=EarningsContext(
            risk_label="EARNINGS_INSIDE_WINDOW",
            days_to_earnings=3,
            earnings_within_window=True,
            earnings_risk_window_days=7,
        ),
        profile=get_balanced_research_default(),
    )
    assert decision.overall_decision == DECISION_ALLOWED
    assert EARNINGS_INSIDE_WINDOW in decision.warning_labels


def test_earnings_inside_window_can_be_promoted_to_block() -> None:
    settings = AppSettings(hard_filter_earnings_inside_window_blocks=True)
    gate = HardFilterGate(settings=settings)
    decision = gate.evaluate(
        stock=_strong_stock(),
        earnings=EarningsContext(
            risk_label="EARNINGS_INSIDE_WINDOW",
            days_to_earnings=3,
            earnings_within_window=True,
            earnings_risk_window_days=7,
        ),
        profile=get_balanced_research_default(),
    )
    assert decision.overall_decision == DECISION_BLOCKED
    assert EARNINGS_INSIDE_WINDOW in decision.stock_blocking_labels


def test_earnings_before_expiration_always_blocks() -> None:
    gate = HardFilterGate(settings=AppSettings())
    decision = gate.evaluate(
        stock=_strong_stock(),
        earnings=EarningsContext(
            risk_label="EARNINGS_BEFORE_EXPIRATION",
            days_to_earnings=2,
            earnings_within_window=True,
            earnings_before_expiration="TRUE",
            earnings_risk_window_days=7,
        ),
        profile=get_balanced_research_default(),
    )
    assert decision.overall_decision == DECISION_BLOCKED
    assert EARNINGS_BEFORE_OPTION_EXPIRATION in decision.stock_blocking_labels


# ---------------------------------------------------------------------------
# Optional option filters (run only when option data exists)
# ---------------------------------------------------------------------------


def test_option_filters_run_when_data_present_and_pass() -> None:
    gate = HardFilterGate(settings=AppSettings())
    decision = gate.evaluate(
        stock=_strong_stock(),
        option=_good_option(),
        profile=get_balanced_research_default(),
    )
    assert decision.overall_decision == DECISION_ALLOWED
    assert decision.option_decision == OPTION_DECISION_ALLOWED
    # No option filters skipped when full data is supplied.
    assert "option_dte" not in decision.skipped_filters


def test_option_dte_too_short_blocks_option_only() -> None:
    gate = HardFilterGate(settings=AppSettings())
    bad = OptionContext(**{**_good_option().__dict__, "dte": 10})
    decision = gate.evaluate(
        stock=_strong_stock(),
        option=bad,
        profile=get_balanced_research_default(),
    )
    assert decision.overall_decision == DECISION_ALLOWED
    assert decision.option_decision == OPTION_DECISION_BLOCKED
    assert DTE_TOO_SHORT in decision.option_blocking_labels


def test_option_spread_too_wide_blocks_option_only() -> None:
    gate = HardFilterGate(settings=AppSettings())
    bad = OptionContext(**{**_good_option().__dict__, "bid": 4.0, "ask": 6.0})
    decision = gate.evaluate(
        stock=_strong_stock(),
        option=bad,
        profile=get_balanced_research_default(),
    )
    assert decision.overall_decision == DECISION_ALLOWED
    assert SPREAD_TOO_WIDE in decision.option_blocking_labels


def test_option_low_open_interest_blocks_option_only() -> None:
    gate = HardFilterGate(settings=AppSettings())
    bad = OptionContext(**{**_good_option().__dict__, "open_interest": 5})
    decision = gate.evaluate(
        stock=_strong_stock(),
        option=bad,
        profile=get_balanced_research_default(),
    )
    assert LOW_OPEN_INTEREST in decision.option_blocking_labels


def test_option_iv_extreme_blocks_option_only() -> None:
    gate = HardFilterGate(settings=AppSettings())
    bad = OptionContext(**{**_good_option().__dict__, "implied_volatility": 0.95})
    decision = gate.evaluate(
        stock=_strong_stock(),
        option=bad,
        profile=get_balanced_research_default(),
    )
    assert decision.overall_decision == DECISION_ALLOWED
    assert IV_TOO_HIGH in decision.option_blocking_labels


def test_option_target_below_breakeven_blocks_option_only() -> None:
    gate = HardFilterGate(settings=AppSettings())
    stock = _strong_stock()
    # target_price 100 with breakeven 105 -> target below breakeven
    stock = StockContext(**{**stock.__dict__, "target_price": 100.0})
    decision = gate.evaluate(
        stock=stock,
        option=_good_option(),
        profile=get_balanced_research_default(),
    )
    assert TARGET_BELOW_BREAKEVEN in decision.option_blocking_labels
    # Stock decision still allowed.
    assert decision.overall_decision == DECISION_ALLOWED


def test_partial_option_data_still_skips_missing_filters() -> None:
    """Only some option fields supplied; missing ones must SKIP not FAIL."""
    gate = HardFilterGate(settings=AppSettings())
    partial = OptionContext(
        option_type="CALL",
        strike=100.0,
        dte=60,
        # No bid/ask -> spread skipped
        # No open_interest -> oi skipped
        # No IV -> iv skipped
    )
    decision = gate.evaluate(
        stock=_strong_stock(),
        option=partial,
        profile=get_balanced_research_default(),
    )
    skipped = set(decision.skipped_filters)
    assert "option_spread" in skipped
    assert "option_open_interest" in skipped
    assert "option_iv_extreme" in skipped
    # DTE is present so it ran and passed.
    assert "option_dte" not in skipped


def test_decision_to_dict_shape_is_stable() -> None:
    gate = HardFilterGate(settings=AppSettings())
    decision = gate.evaluate(stock=_strong_stock(), profile=get_balanced_research_default())
    payload = decision.to_dict()
    expected_keys = {
        "symbol",
        "overall_decision",
        "option_decision",
        "outcomes",
        "stock_blocking_labels",
        "option_blocking_labels",
        "warning_labels",
        "skipped_filters",
        "reasons",
        "profile_name",
        "profile_version",
        "stock_risk_reward",
        "price_extension_atr",
        "price_extension_sma50_percent",
        "regime_label",
        "earnings_risk_label",
    }
    assert expected_keys.issubset(set(payload.keys()))


# ---------------------------------------------------------------------------
# DB-path: HardFilterService + persistence + route
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
    _seed_setup("AMD")
    _seed_regime("RISK_ON")
    _seed_earnings("AMD")

    session = _TestSession()
    try:
        service = HardFilterService()
        evaluation = service.evaluate_symbol(session, "amd", persist=True)
    finally:
        session.close()

    assert evaluation.decision.symbol == "AMD"
    assert evaluation.decision.overall_decision == DECISION_ALLOWED
    assert evaluation.decision.option_decision == OPTION_DECISION_NOT_EVALUATED
    assert evaluation.record is not None
    assert evaluation.record.overall_decision == DECISION_ALLOWED


def test_service_persistence_is_idempotent() -> None:
    _seed_setup("AMD")
    _seed_regime("RISK_ON")
    _seed_earnings("AMD")

    session = _TestSession()
    try:
        service = HardFilterService()
        service.evaluate_symbol(session, "AMD", persist=True)
        service.evaluate_symbol(session, "AMD", persist=True)
        count = session.query(HardFilterResult).count()
    finally:
        session.close()
    assert count == 1


def test_service_skips_persist_when_persist_false() -> None:
    _seed_setup("AMD")

    session = _TestSession()
    try:
        service = HardFilterService()
        evaluation = service.evaluate_symbol(session, "AMD", persist=False)
        count = session.query(HardFilterResult).count()
    finally:
        session.close()
    assert evaluation.record is None
    assert count == 0


def test_service_blocks_when_setup_has_weak_risk_reward() -> None:
    _seed_setup("AMD", stock_risk_reward=1.0)
    _seed_regime("RISK_ON")
    _seed_earnings("AMD")

    session = _TestSession()
    try:
        service = HardFilterService()
        evaluation = service.evaluate_symbol(session, "AMD", persist=True)
    finally:
        session.close()
    assert evaluation.decision.overall_decision == DECISION_BLOCKED
    assert WEAK_STOCK_RISK_REWARD in evaluation.decision.stock_blocking_labels


def test_service_records_regime_warning_in_decision() -> None:
    _seed_setup("AMD")
    _seed_regime("RISK_OFF")
    _seed_earnings("AMD")

    session = _TestSession()
    try:
        service = HardFilterService()
        evaluation = service.evaluate_symbol(session, "AMD", persist=True)
    finally:
        session.close()
    assert evaluation.decision.overall_decision == DECISION_ALLOWED
    assert REGIME_OPPOSES_SETUP in evaluation.decision.warning_labels


def test_route_returns_decision_shape() -> None:
    _seed_setup("AMD")
    _seed_regime("RISK_ON")
    _seed_earnings("AMD")

    client = TestClient(app)
    response = client.get("/api/hard-filters/AMD")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "OK"
    decision = body["decision"]
    assert decision["symbol"] == "AMD"
    assert decision["overall_decision"] == DECISION_ALLOWED
    assert decision["option_decision"] == OPTION_DECISION_NOT_EVALUATED
    # GET without ?persist=true does not write to DB.
    assert body["record_id"] is None


def test_route_persists_when_requested() -> None:
    _seed_setup("AMD")
    _seed_regime("RISK_ON")
    _seed_earnings("AMD")

    client = TestClient(app)
    response = client.get("/api/hard-filters/AMD?persist=true")
    assert response.status_code == 200
    body = response.json()
    assert body["record_id"] is not None

    list_response = client.get("/api/hard-filters?symbol=AMD")
    assert list_response.status_code == 200
    listing = list_response.json()
    assert listing["count"] == 1
    assert listing["results"][0]["overall_decision"] == DECISION_ALLOWED


def test_route_rejects_empty_symbol() -> None:
    client = TestClient(app)
    response = client.get("/api/hard-filters/%20")
    assert response.status_code == 400


def test_route_returns_404_for_unknown_option_snapshot() -> None:
    _seed_setup("AMD")
    client = TestClient(app)
    response = client.get("/api/hard-filters/AMD?manual_option_snapshot_id=9999")
    assert response.status_code == 404
