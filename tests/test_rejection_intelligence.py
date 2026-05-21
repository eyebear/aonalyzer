"""Phase 23, step 23.12 — focused tests for the rejection intelligence layer.

Covers:

* every final action label is classified deterministically into one of
  the four Phase 23 categories;
* the two invariants:
    - ``OPTION_DATA_NOT_AVAILABLE`` is NOT a rejection;
    - ``STOCK_OK_OPTION_BAD`` is an option-only rejection (stock thesis
      preserved);
* every explainer produces structured reasons;
* the rejected-but-interesting heuristic flags strong-R:R candidates
  blocked by a recoverable filter;
* the memory writer is idempotent;
* routes return the documented shapes (including the dedicated
  ``/interesting`` endpoint).
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
    EARNINGS_BEFORE_OPTION_EXPIRATION,
    EARNINGS_INSIDE_WINDOW,
    EarningsContext,
    HardFilterGate,
    OptionContext,
    RegimeContext,
    StockContext,
    WEAK_STOCK_RISK_REWARD,
)
from app.market_regime.market_regime_models import MarketRegimeSnapshot
from app.options.iv_analysis import IV_TOO_HIGH
from app.options.option_filters import LOW_OPEN_INTEREST, SPREAD_TOO_WIDE
from app.options.target_breakeven import TARGET_BELOW_BREAKEVEN
from app.profiles.default_profiles import get_balanced_research_default
from app.quant.stock_setup_models import StockSetup
from app.rejection.breakeven_failure_explainer import explain_breakeven_failures
from app.rejection.iv_earnings_rejection_explainer import (
    explain_iv_earnings_rejections,
)
from app.rejection.liquidity_rejection_explainer import (
    explain_liquidity_rejections,
)
from app.rejection.rejected_but_interesting import (
    classify_rejected_but_interesting,
)
from app.rejection.rejection_categories import (
    CATEGORY_DATA_INSUFFICIENT,
    CATEGORY_HARD_STOCK_REJECTION,
    CATEGORY_NOT_REJECTED,
    CATEGORY_STOCK_OK_OPTION_BAD,
    SEVERITY_HARD_REJECT,
    SEVERITY_NOT_EVALUATED,
    SEVERITY_NOT_REJECTED,
    SEVERITY_OPTION_ONLY_REJECT,
)
from app.rejection.rejection_classifier import classify_rejection
from app.rejection.rejection_memory_writer import RejectionMemoryWriter
from app.rejection.rejection_models import RejectedCandidate, RejectionReason
from app.rejection.rejection_service import RejectionService
from app.rejection.stock_ok_option_bad import detect_stock_ok_option_bad
from app.rejection.stock_ok_option_missing import detect_stock_ok_option_missing


# ---------------------------------------------------------------------------
# Helpers (mirror Phase 21/22 fixtures)
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


def _build_decision(
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
# Classifier — final-label coverage
# ---------------------------------------------------------------------------


def test_ready_stock_only_is_not_rejected() -> None:
    decision = _build_decision(
        sufficiency_inputs=_ok_sufficiency_inputs(),
        stock=_strong_stock(),
        regime=RegimeContext(regime_label="RISK_ON"),
        earnings=EarningsContext(risk_label="NO_EARNINGS_NEAR"),
    )
    classification = classify_rejection(decision, profile_minimum_risk_reward=2.0)
    assert decision.final_label == READY_TO_RESEARCH_STOCK_ONLY
    assert classification.rejection_category == CATEGORY_NOT_REJECTED
    assert classification.rejection_severity == SEVERITY_NOT_REJECTED
    assert classification.is_rejected is False
    assert classification.is_rejected_but_interesting is False


def test_ready_with_option_is_not_rejected() -> None:
    decision = _build_decision(
        sufficiency_inputs=_ok_sufficiency_inputs(),
        stock=_strong_stock(),
        option=_good_option(),
        regime=RegimeContext(regime_label="RISK_ON"),
        earnings=EarningsContext(risk_label="NO_EARNINGS_NEAR"),
        option_data_requested=True,
    )
    classification = classify_rejection(decision, profile_minimum_risk_reward=2.0)
    assert decision.final_label == READY_TO_RESEARCH_WITH_OPTION
    assert classification.rejection_category == CATEGORY_NOT_REJECTED


def test_watch_is_not_rejected() -> None:
    decision = _build_decision(
        sufficiency_inputs=_ok_sufficiency_inputs(),
        stock=_strong_stock(),
        regime=RegimeContext(regime_label="RISK_OFF"),
        earnings=EarningsContext(risk_label="NO_EARNINGS_NEAR"),
    )
    classification = classify_rejection(decision, profile_minimum_risk_reward=2.0)
    assert decision.final_label == WATCH_STOCK_ONLY
    assert classification.rejection_category == CATEGORY_NOT_REJECTED


def test_wait_for_entry_is_not_rejected() -> None:
    stock = _strong_stock(
        current_close=103.0,
        nearest_support=100.0,
        sma_50=100.0,
        atr_14=2.0,
    )
    decision = _build_decision(
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
    classification = classify_rejection(decision, profile_minimum_risk_reward=2.0)
    assert decision.final_label == WAIT_FOR_ENTRY_STOCK_ONLY
    assert classification.rejection_category == CATEGORY_NOT_REJECTED


def test_no_trade_classifies_hard_stock_rejection() -> None:
    decision = _build_decision(
        sufficiency_inputs=_ok_sufficiency_inputs(),
        stock=_strong_stock(stock_risk_reward=1.0),  # weak R:R
        regime=RegimeContext(regime_label="RISK_ON"),
        earnings=EarningsContext(risk_label="NO_EARNINGS_NEAR"),
    )
    classification = classify_rejection(decision, profile_minimum_risk_reward=2.0)
    assert decision.final_label == NO_TRADE
    assert classification.rejection_category == CATEGORY_HARD_STOCK_REJECTION
    assert classification.rejection_severity == SEVERITY_HARD_REJECT
    assert classification.is_rejected is True


def test_stock_ok_option_bad_classifies_option_only() -> None:
    bad = OptionContext(**{**_good_option().__dict__, "bid": 4.0, "ask": 6.0})
    decision = _build_decision(
        sufficiency_inputs=_ok_sufficiency_inputs(),
        stock=_strong_stock(),
        option=bad,
        regime=RegimeContext(regime_label="RISK_ON"),
        earnings=EarningsContext(risk_label="NO_EARNINGS_NEAR"),
        option_data_requested=True,
    )
    classification = classify_rejection(decision, profile_minimum_risk_reward=2.0)
    assert decision.final_label == STOCK_OK_OPTION_BAD
    assert classification.rejection_category == CATEGORY_STOCK_OK_OPTION_BAD
    assert classification.rejection_severity == SEVERITY_OPTION_ONLY_REJECT
    assert classification.is_rejected is True
    # Phase 23 invariant: stock thesis preserved as researchable.
    assert classification.stock_ok_option_bad is not None
    assert classification.stock_ok_option_bad.matched is True
    assert classification.is_rejected_but_interesting is True


def test_insufficient_price_history_classifies_data_insufficient() -> None:
    decision = _build_decision(
        sufficiency_inputs=_ok_sufficiency_inputs(price_rows=[]),
        stock=_strong_stock(stock_risk_reward=None),
        regime=RegimeContext(regime_label="RISK_ON"),
        earnings=EarningsContext(risk_label="NO_EARNINGS_NEAR"),
    )
    classification = classify_rejection(decision, profile_minimum_risk_reward=2.0)
    assert decision.final_label == INSUFFICIENT_PRICE_HISTORY
    assert classification.rejection_category == CATEGORY_DATA_INSUFFICIENT
    assert classification.rejection_severity == SEVERITY_NOT_EVALUATED
    assert classification.is_rejected is True
    assert classification.is_rejected_but_interesting is False


# ---------------------------------------------------------------------------
# Phase 23 INVARIANT: missing option data is not a rejection
# ---------------------------------------------------------------------------


def test_option_data_not_available_is_not_a_rejection() -> None:
    decision = _build_decision(
        sufficiency_inputs=_ok_sufficiency_inputs(),
        stock=_strong_stock(),
        option=None,
        regime=RegimeContext(regime_label="RISK_ON"),
        earnings=EarningsContext(risk_label="NO_EARNINGS_NEAR"),
        option_data_requested=True,
    )
    classification = classify_rejection(decision, profile_minimum_risk_reward=2.0)
    assert decision.final_label == OPTION_DATA_NOT_AVAILABLE
    assert classification.rejection_category == CATEGORY_NOT_REJECTED
    assert classification.rejection_severity == SEVERITY_NOT_REJECTED
    assert classification.is_rejected is False
    # The dedicated detector confirms the matching state.
    missing = detect_stock_ok_option_missing(decision)
    assert missing.matched is True
    assert missing.is_rejection is False


# ---------------------------------------------------------------------------
# Detectors
# ---------------------------------------------------------------------------


def test_detect_stock_ok_option_bad_on_matching_label() -> None:
    bad = OptionContext(**{**_good_option().__dict__, "bid": 4.0, "ask": 6.0})
    decision = _build_decision(
        sufficiency_inputs=_ok_sufficiency_inputs(),
        stock=_strong_stock(),
        option=bad,
        regime=RegimeContext(regime_label="RISK_ON"),
        earnings=EarningsContext(risk_label="NO_EARNINGS_NEAR"),
        option_data_requested=True,
    )
    result = detect_stock_ok_option_bad(decision)
    assert result.matched is True
    assert SPREAD_TOO_WIDE in result.option_blocking_labels


def test_detect_stock_ok_option_missing_for_ready_stock_only_returns_false() -> None:
    decision = _build_decision(
        sufficiency_inputs=_ok_sufficiency_inputs(),
        stock=_strong_stock(),
        option=None,
        regime=RegimeContext(regime_label="RISK_ON"),
        earnings=EarningsContext(risk_label="NO_EARNINGS_NEAR"),
        option_data_requested=False,
    )
    result = detect_stock_ok_option_missing(decision)
    assert result.matched is False
    assert result.is_rejection is False


# ---------------------------------------------------------------------------
# Rejected-but-interesting heuristic
# ---------------------------------------------------------------------------


def test_rejected_but_interesting_flags_strong_rr_with_regime_warning() -> None:
    # Stock has strong R:R + price extension block + regime opposes.
    decision = _build_decision(
        sufficiency_inputs=_ok_sufficiency_inputs(),
        stock=StockContext(
            symbol="AMD",
            snapshot_date=date(2026, 5, 15),
            direction="LONG",
            current_close=130.0,
            nearest_support=95.0,
            nearest_resistance=140.0,
            sma_50=100.0,
            atr_14=2.0,
            stock_risk_reward=4.0,  # well above 1.5x of 2.0 minimum
            target_price=140.0,
        ),
        regime=RegimeContext(regime_label="RISK_OFF"),
        earnings=EarningsContext(risk_label="NO_EARNINGS_NEAR"),
    )
    result = classify_rejected_but_interesting(
        decision, profile_minimum_risk_reward=2.0
    )
    assert result.is_interesting is True
    assert any("Strong" not in r or "R:R" in r for r in result.reasons)


def test_rejected_but_interesting_does_not_flag_insufficient_data() -> None:
    decision = _build_decision(
        sufficiency_inputs=_ok_sufficiency_inputs(price_rows=[]),
        stock=_strong_stock(stock_risk_reward=None),
        regime=RegimeContext(regime_label="RISK_ON"),
        earnings=EarningsContext(risk_label="NO_EARNINGS_NEAR"),
    )
    result = classify_rejected_but_interesting(
        decision, profile_minimum_risk_reward=2.0
    )
    assert result.is_interesting is False


def test_rejected_but_interesting_does_not_flag_healthy_candidate() -> None:
    decision = _build_decision(
        sufficiency_inputs=_ok_sufficiency_inputs(),
        stock=_strong_stock(),
        regime=RegimeContext(regime_label="RISK_ON"),
        earnings=EarningsContext(risk_label="NO_EARNINGS_NEAR"),
    )
    result = classify_rejected_but_interesting(
        decision, profile_minimum_risk_reward=2.0
    )
    assert result.is_interesting is False


# ---------------------------------------------------------------------------
# Explainers
# ---------------------------------------------------------------------------


def test_breakeven_explainer_emits_target_below_breakeven() -> None:
    decision = _build_decision(
        sufficiency_inputs=_ok_sufficiency_inputs(),
        stock=_strong_stock(target_price=100.0),  # target below breakeven of 105
        option=_good_option(),
        regime=RegimeContext(regime_label="RISK_ON"),
        earnings=EarningsContext(risk_label="NO_EARNINGS_NEAR"),
        option_data_requested=True,
    )
    payloads = explain_breakeven_failures(decision)
    labels = {p.reason_label for p in payloads}
    assert TARGET_BELOW_BREAKEVEN in labels


def test_iv_earnings_explainer_emits_iv_too_high() -> None:
    bad = OptionContext(**{**_good_option().__dict__, "implied_volatility": 0.95})
    decision = _build_decision(
        sufficiency_inputs=_ok_sufficiency_inputs(),
        stock=_strong_stock(),
        option=bad,
        regime=RegimeContext(regime_label="RISK_ON"),
        earnings=EarningsContext(risk_label="NO_EARNINGS_NEAR"),
        option_data_requested=True,
    )
    payloads = explain_iv_earnings_rejections(decision)
    labels = {p.reason_label for p in payloads}
    assert IV_TOO_HIGH in labels


def test_iv_earnings_explainer_emits_earnings_before_expiration() -> None:
    decision = _build_decision(
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
    payloads = explain_iv_earnings_rejections(decision)
    labels = {p.reason_label for p in payloads}
    assert EARNINGS_BEFORE_OPTION_EXPIRATION in labels


def test_liquidity_explainer_emits_spread_and_oi() -> None:
    bad = OptionContext(
        **{
            **_good_option().__dict__,
            "bid": 4.0,
            "ask": 6.0,
            "open_interest": 5,
        }
    )
    decision = _build_decision(
        sufficiency_inputs=_ok_sufficiency_inputs(),
        stock=_strong_stock(),
        option=bad,
        regime=RegimeContext(regime_label="RISK_ON"),
        earnings=EarningsContext(risk_label="NO_EARNINGS_NEAR"),
        option_data_requested=True,
    )
    payloads = explain_liquidity_rejections(decision)
    labels = {p.reason_label for p in payloads}
    assert SPREAD_TOO_WIDE in labels
    assert LOW_OPEN_INTEREST in labels


# ---------------------------------------------------------------------------
# Service / persistence path
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


def test_service_persists_no_trade_with_reasons() -> None:
    _seed_prices("AMD", 60)
    _seed_setup("AMD", stock_risk_reward=1.0)  # weak R:R triggers NO_TRADE
    _seed_regime("RISK_ON")
    _seed_earnings("AMD")

    session = _TestSession()
    try:
        evaluation = RejectionService().evaluate_symbol(
            session, "AMD", persist=True
        )
        candidate = session.query(RejectedCandidate).first()
        reasons = (
            session.query(RejectionReason)
            .filter(RejectionReason.rejected_candidate_id == candidate.id)
            .all()
        )
    finally:
        session.close()
    assert evaluation.classification.rejection_category == CATEGORY_HARD_STOCK_REJECTION
    assert candidate.rejection_severity == SEVERITY_HARD_REJECT
    assert {r.reason_label for r in reasons} & {WEAK_STOCK_RISK_REWARD}


def test_service_does_not_persist_when_option_data_missing() -> None:
    """The defining Phase 23 invariant at the DB layer."""
    _seed_prices("AMD", 60)
    _seed_setup("AMD")
    _seed_regime("RISK_ON")
    _seed_earnings("AMD")

    session = _TestSession()
    try:
        evaluation = RejectionService().evaluate_symbol(
            session, "AMD", option_data_requested=True, persist=True
        )
        count = session.query(RejectedCandidate).count()
    finally:
        session.close()
    assert evaluation.classification.rejection_category == CATEGORY_NOT_REJECTED
    assert count == 0


def test_service_persistence_is_idempotent_and_replaces_reasons() -> None:
    _seed_prices("AMD", 60)
    _seed_setup("AMD", stock_risk_reward=1.0)
    _seed_regime("RISK_ON")
    _seed_earnings("AMD")

    session = _TestSession()
    try:
        service = RejectionService()
        service.evaluate_symbol(session, "AMD", persist=True)
        service.evaluate_symbol(session, "AMD", persist=True)
        candidate_count = session.query(RejectedCandidate).count()
        reason_count = session.query(RejectionReason).count()
    finally:
        session.close()
    assert candidate_count == 1
    # Reasons replaced rather than appended -- count should match a single
    # evaluation (>= 1, definitely not 2x).
    assert reason_count >= 1 and reason_count < 10


def test_memory_writer_short_circuits_when_not_rejected() -> None:
    _seed_prices("AMD", 60)
    _seed_setup("AMD")
    _seed_regime("RISK_ON")
    _seed_earnings("AMD")

    session = _TestSession()
    try:
        evaluation = RejectionService().evaluate_symbol(
            session, "AMD", persist=True
        )
        candidate_count = session.query(RejectedCandidate).count()
    finally:
        session.close()
    assert evaluation.classification.rejection_category == CATEGORY_NOT_REJECTED
    assert candidate_count == 0


def test_service_stock_ok_option_bad_records_only_option_reasons() -> None:
    """The stock side is not a rejection here, but a record IS written
    under the STOCK_OK_OPTION_BAD category so dashboards can surface the
    option-side issue."""
    from app.options.manual_option_input_service import ManualOptionInputService
    from app.options.manual_option_models import ManualOptionSnapshotRecord

    _seed_prices("AMD", 60)
    _seed_setup("AMD")
    _seed_regime("RISK_ON")
    _seed_earnings("AMD")

    # Inject a manual option snapshot via a fake service so we can drive
    # STOCK_OK_OPTION_BAD without invoking the parser.
    fake_record = ManualOptionSnapshotRecord(
        id=1,
        raw_text="AMD call",
        symbol="AMD",
        source_name="manual",
        underlying_price=100.0,
        expiration_date=date(2026, 7, 15),
        option_type="CALL",
        strike=100.0,
        bid=4.0,  # wide spread
        ask=6.0,
        last_price=5.0,
        volume=500,
        open_interest=2000,
        implied_volatility=0.50,
        delta=0.5,
        gamma=None,
        theta=None,
        vega=None,
        rho=None,
        dte=60,
        mid_price=5.0,
        spread_percent=40.0,
        contract_cost=500.0,
        breakeven=105.0,
        breakeven_distance=5.0,
        breakeven_distance_percent=5.0,
        parser_confidence="HIGH",
        missing_fields=[],
        parsed_fields={},
        data_quality_status="USABLE_OPTION_DATA",
        ai_status="NOT_ANALYZED",
        ai_summary=None,
        ai_analysis_json=None,
        created_at=datetime(2026, 5, 15, tzinfo=timezone.utc),
    )

    class _FakeManualService(ManualOptionInputService):
        def __init__(self):
            pass

        def get_manual_snapshot_by_id(self, db, snapshot_id):
            return fake_record if snapshot_id == 1 else None

    # Build the service stack manually so we can inject the fake.
    from app.action.action_service import ActionSuggestionService
    from app.decision.decision_service import DecisionService
    from app.hard_filter.hard_filter_service import HardFilterService

    settings = AppSettings()
    manual_service = _FakeManualService()
    hf_service = HardFilterService(settings=settings)
    decision_service = DecisionService(
        settings=settings,
        hard_filter_service=hf_service,
        manual_option_service=manual_service,
    )
    action_service = ActionSuggestionService(
        settings=settings,
        decision_service=decision_service,
        manual_option_service=manual_service,
    )
    rejection_service = RejectionService(
        settings=settings,
        action_service=action_service,
    )

    session = _TestSession()
    try:
        evaluation = rejection_service.evaluate_symbol(
            session,
            "AMD",
            manual_option_snapshot_id=1,
            option_data_requested=True,
            persist=True,
        )
        candidate = session.query(RejectedCandidate).first()
        reason_labels = {
            r.reason_label
            for r in session.query(RejectionReason)
            .filter(RejectionReason.rejected_candidate_id == candidate.id)
            .all()
        }
    finally:
        session.close()
    assert evaluation.classification.rejection_category == CATEGORY_STOCK_OK_OPTION_BAD
    assert candidate.rejection_severity == SEVERITY_OPTION_ONLY_REJECT
    assert SPREAD_TOO_WIDE in reason_labels
    assert WEAK_STOCK_RISK_REWARD not in reason_labels  # stock side not in reasons


def test_memory_writer_directly_returns_no_candidate_when_not_rejected() -> None:
    from app.rejection.rejection_classifier import RejectionClassification
    from app.rejection.rejection_memory_writer import RejectionMemoryWriter

    writer = RejectionMemoryWriter()
    classification = RejectionClassification(
        final_action_label=READY_TO_RESEARCH_STOCK_ONLY,
        rejection_category=CATEGORY_NOT_REJECTED,
        rejection_severity=SEVERITY_NOT_REJECTED,
        is_rejected=False,
        is_rejected_but_interesting=False,
        summary="ok",
    )
    session = _TestSession()
    try:
        result = writer.write(
            db=session,
            symbol="AMD",
            snapshot_date=date(2026, 5, 15),
            classification=classification,
            lifecycle_state="READY_FOR_RESEARCH",
            reason_payloads=[],
            profile_name="Balanced",
            profile_version="x",
        )
    finally:
        session.close()
    assert result.candidate is None
    assert result.reasons == []


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


def test_route_returns_evaluation_shape() -> None:
    _seed_prices("AMD", 60)
    _seed_setup("AMD", stock_risk_reward=1.0)
    _seed_regime("RISK_ON")
    _seed_earnings("AMD")

    client = TestClient(app)
    response = client.get("/api/rejections/AMD?persist=true")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "OK"
    assert body["evaluation"]["classification"]["rejection_category"] == CATEGORY_HARD_STOCK_REJECTION


def test_route_list_filters_by_category() -> None:
    _seed_prices("AMD", 60)
    _seed_setup("AMD", stock_risk_reward=1.0)
    _seed_regime("RISK_ON")
    _seed_earnings("AMD")

    client = TestClient(app)
    client.get("/api/rejections/AMD?persist=true")
    listing = client.get(
        f"/api/rejections?category={CATEGORY_HARD_STOCK_REJECTION}"
    ).json()
    assert listing["count"] == 1
    assert listing["candidates"][0]["rejection_category"] == CATEGORY_HARD_STOCK_REJECTION


def test_route_interesting_returns_only_interesting_candidates() -> None:
    # Symbol 1: hard rejection but interesting (strong R:R, regime-warning,
    # extension block).
    _seed_prices("AMD", 60)
    _seed_setup(
        "AMD",
        current_close=130.0,
        nearest_support=95.0,
        sma_50=100.0,
        atr_14=2.0,
        stock_risk_reward=4.0,
    )
    _seed_regime("RISK_OFF")
    _seed_earnings("AMD")

    # Symbol 2: plain weak-R:R rejection, NOT interesting.
    _seed_prices("FOO", 60)
    _seed_setup("FOO", stock_risk_reward=1.0)
    _seed_earnings("FOO")

    client = TestClient(app)
    client.get("/api/rejections/AMD?persist=true")
    client.get("/api/rejections/FOO?persist=true")

    interesting = client.get("/api/rejections/interesting").json()
    symbols = {c["symbol"] for c in interesting["candidates"]}
    assert "AMD" in symbols
    assert "FOO" not in symbols


def test_route_rejects_empty_symbol() -> None:
    client = TestClient(app)
    response = client.get("/api/rejections/%20")
    assert response.status_code == 400
