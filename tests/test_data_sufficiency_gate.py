"""Phase 19, step 19.11 — focused tests for the data sufficiency gate.

These tests intentionally exercise the new gate-level guarantees that
existing Phase 6 / Phase 12 / Phase 15 tests do not cover:

* missing options never block stock-only analysis;
* missing prices block stock analysis;
* the legacy ``INSUFFICIENT_SETUP_DATA`` setup status maps to the Phase 19
  ``INSUFFICIENT_STOCK_SETUP_DATA`` blocking label;
* news / IV / earnings / memory insufficiency are warnings or confidence
  reducers by default;
* profile flags promote those warnings to stock blockers;
* an option present-but-unusable yields ``INSUFFICIENT_OPTION_DATA`` on the
  option status and does **not** block the stock decision;
* the action builder emits a practical suggestion per Phase 19 label;
* the ``/api/data-quality/sufficiency/{symbol}`` route returns the same shape.
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
from app.api.routes import data_quality_routes
from app.data_quality.data_sufficiency_gate import (
    DataSufficiencyGate,
    GateDecision,
    INSUFFICIENT_OPTION_DATA,
    OPTION_DATA_NOT_AVAILABLE,
    OPTION_OK,
    STOCK_DECISION_ALLOWED,
    STOCK_DECISION_BLOCKED,
    SufficiencyInputs,
)
from app.data_quality.data_sufficiency_labels import DataSufficiencyLabel
from app.data_quality.insufficient_data_action_builder import (
    ACTION_PASTE_MANUAL_OPTION,
    ACTION_REFRESH_EARNINGS,
    ACTION_REFRESH_IV_RISK,
    ACTION_REFRESH_MARKET_DATA,
    ACTION_REFRESH_NEWS,
    ACTION_REPASTE_MANUAL_OPTION,
    ACTION_RUN_STOCK_SETUP_DETECTION,
    InsufficientDataActionBuilder,
)
from app.database.base import Base
from app.database.models import DailyPrice
from app.earnings.earnings_models import EarningsEvent
from app.iv_history.iv_models import IvHistoryDay
from app.profiles.default_profiles import get_balanced_research_default
from app.quant.stock_setup_models import StockSetup


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _price_rows(count: int) -> list[dict]:
    base = date(2026, 1, 2)
    rows = []
    for i in range(count):
        rows.append(
            {
                "date": base + timedelta(days=i),
                "open": 100.0 + i,
                "high": 101.0 + i,
                "low": 99.0 + i,
                "close": 100.5 + i,
                "volume": 1_000_000 + i,
            }
        )
    return rows


def _ok_option_rows() -> list[dict]:
    return [
        {
            "bid": 1.2,
            "ask": 1.4,
            "open_interest": 200,
            "implied_volatility": 0.45,
        }
    ]


def _bad_option_rows() -> list[dict]:
    """Option present but missing fields -> INSUFFICIENT_OPTION_DATA."""
    return [
        {
            "bid": 1.2,
            "ask": 1.4,
            "open_interest": 200,
            "implied_volatility": None,
        }
    ]


def _news_rows(count: int) -> list[dict]:
    return [
        {
            "source": "Yahoo Finance",
            "title": f"AMD update {i}",
            "event_time": datetime(2026, 5, 10, tzinfo=timezone.utc),
        }
        for i in range(count)
    ]


# ---------------------------------------------------------------------------
# Pure-input gate tests (Phase 19 steps 19.2 — 19.9)
# ---------------------------------------------------------------------------


def test_missing_options_do_not_block_stock_only_decision() -> None:
    """The defining Phase 19 invariant."""
    gate = DataSufficiencyGate()
    decision = gate.evaluate_inputs(
        SufficiencyInputs(
            symbol="AMD",
            price_rows=_price_rows(60),
            stock_setup_status="SUFFICIENT",
            option_rows=None,
            news_rows=_news_rows(3),
            iv_history_rows=[
                {"snapshot_date": date(2026, 5, 1), "atm_iv_30d": 0.5}
                for _ in range(40)
            ],
            earnings_rows=[
                {"symbol": "AMD", "earnings_datetime_utc": datetime(2026, 7, 1, tzinfo=timezone.utc), "source": "test"}
            ],
            memory_rows=[{"id": 1}],
        ),
        profile=None,
    )

    assert isinstance(decision, GateDecision)
    assert decision.stock_decision_status == STOCK_DECISION_ALLOWED
    assert decision.option_status == OPTION_DATA_NOT_AVAILABLE
    assert OPTION_DATA_NOT_AVAILABLE in decision.non_blocking_labels
    assert decision.blocking_labels == []


def test_missing_price_history_blocks_stock_decision() -> None:
    gate = DataSufficiencyGate()
    decision = gate.evaluate_inputs(
        SufficiencyInputs(
            symbol="AMD",
            price_rows=[],
            stock_setup_status="SUFFICIENT",
            option_rows=_ok_option_rows(),
            news_rows=_news_rows(3),
            iv_history_rows=[
                {"snapshot_date": date(2026, 5, 1), "atm_iv_30d": 0.5}
                for _ in range(40)
            ],
            earnings_rows=[{"symbol": "AMD"}],
            memory_rows=[{"id": 1}],
        ),
    )

    assert decision.stock_decision_status == STOCK_DECISION_BLOCKED
    assert DataSufficiencyLabel.INSUFFICIENT_PRICE_HISTORY.value in decision.blocking_labels


def test_legacy_insufficient_setup_data_maps_to_phase19_blocking_label() -> None:
    gate = DataSufficiencyGate()
    decision = gate.evaluate_inputs(
        SufficiencyInputs(
            symbol="AMD",
            price_rows=_price_rows(60),
            stock_setup_status="INSUFFICIENT_SETUP_DATA",
            stock_setup_reasons=["Setup math undefined."],
            option_rows=None,
            news_rows=_news_rows(3),
            iv_history_rows=[
                {"snapshot_date": date(2026, 5, 1), "atm_iv_30d": 0.5}
                for _ in range(40)
            ],
            earnings_rows=[{"symbol": "AMD"}],
            memory_rows=[{"id": 1}],
        ),
    )

    assert decision.stock_decision_status == STOCK_DECISION_BLOCKED
    assert (
        DataSufficiencyLabel.INSUFFICIENT_STOCK_SETUP_DATA.value
        in decision.blocking_labels
    )
    # The legacy label must NOT leak into the gate's public output.
    assert (
        DataSufficiencyLabel.INSUFFICIENT_SETUP_DATA.value
        not in decision.blocking_labels
    )


def test_phase19_setup_label_passes_through() -> None:
    gate = DataSufficiencyGate()
    decision = gate.evaluate_inputs(
        SufficiencyInputs(
            symbol="AMD",
            price_rows=_price_rows(60),
            stock_setup_status="INSUFFICIENT_STOCK_SETUP_DATA",
            option_rows=None,
        ),
    )
    assert decision.stock_decision_status == STOCK_DECISION_BLOCKED
    assert (
        DataSufficiencyLabel.INSUFFICIENT_STOCK_SETUP_DATA.value
        in decision.blocking_labels
    )


def test_sufficient_setup_status_does_not_block() -> None:
    gate = DataSufficiencyGate()
    decision = gate.evaluate_inputs(
        SufficiencyInputs(
            symbol="AMD",
            price_rows=_price_rows(60),
            stock_setup_status="SUFFICIENT",
            option_rows=_ok_option_rows(),
        ),
    )
    assert decision.stock_decision_status == STOCK_DECISION_ALLOWED


def test_missing_news_is_non_blocking_by_default() -> None:
    gate = DataSufficiencyGate()
    decision = gate.evaluate_inputs(
        SufficiencyInputs(
            symbol="AMD",
            price_rows=_price_rows(60),
            stock_setup_status="SUFFICIENT",
            option_rows=_ok_option_rows(),
            news_rows=[],
        ),
        profile=get_balanced_research_default(),
    )

    assert decision.stock_decision_status == STOCK_DECISION_ALLOWED
    assert (
        DataSufficiencyLabel.INSUFFICIENT_NEWS_DATA.value
        in decision.non_blocking_labels
    )
    assert (
        DataSufficiencyLabel.INSUFFICIENT_NEWS_DATA.value
        not in decision.blocking_labels
    )


def test_profile_required_news_promotes_to_blocking() -> None:
    profile = get_balanced_research_default().model_copy(
        update={"requires_news_data": True}
    )
    gate = DataSufficiencyGate()
    decision = gate.evaluate_inputs(
        SufficiencyInputs(
            symbol="AMD",
            price_rows=_price_rows(60),
            stock_setup_status="SUFFICIENT",
            option_rows=_ok_option_rows(),
            news_rows=[],
        ),
        profile=profile,
    )

    assert decision.stock_decision_status == STOCK_DECISION_BLOCKED
    assert (
        DataSufficiencyLabel.INSUFFICIENT_NEWS_DATA.value in decision.blocking_labels
    )


def test_incomplete_option_blocks_option_suitability_only() -> None:
    gate = DataSufficiencyGate()
    decision = gate.evaluate_inputs(
        SufficiencyInputs(
            symbol="AMD",
            price_rows=_price_rows(60),
            stock_setup_status="SUFFICIENT",
            option_rows=_bad_option_rows(),
            news_rows=_news_rows(2),
        ),
    )

    assert decision.option_status == INSUFFICIENT_OPTION_DATA
    assert (
        DataSufficiencyLabel.INSUFFICIENT_OPTION_DATA.value
        in decision.non_blocking_labels
    )
    # Crucially, the stock decision is unaffected.
    assert decision.stock_decision_status == STOCK_DECISION_ALLOWED
    assert (
        DataSufficiencyLabel.INSUFFICIENT_OPTION_DATA.value
        not in decision.blocking_labels
    )


def test_iv_history_insufficient_is_non_blocking_by_default() -> None:
    gate = DataSufficiencyGate()
    decision = gate.evaluate_inputs(
        SufficiencyInputs(
            symbol="AMD",
            price_rows=_price_rows(60),
            stock_setup_status="SUFFICIENT",
            option_rows=_ok_option_rows(),
            iv_history_rows=[],
        ),
        profile=get_balanced_research_default(),
    )
    assert decision.stock_decision_status == STOCK_DECISION_ALLOWED
    assert (
        DataSufficiencyLabel.INSUFFICIENT_IV_DATA.value
        in decision.non_blocking_labels
    )


def test_earnings_missing_is_non_blocking_by_default() -> None:
    gate = DataSufficiencyGate()
    decision = gate.evaluate_inputs(
        SufficiencyInputs(
            symbol="AMD",
            price_rows=_price_rows(60),
            stock_setup_status="SUFFICIENT",
            option_rows=_ok_option_rows(),
            earnings_rows=[],
        ),
        profile=get_balanced_research_default(),
    )
    assert decision.stock_decision_status == STOCK_DECISION_ALLOWED
    assert (
        DataSufficiencyLabel.INSUFFICIENT_EARNINGS_DATA.value
        in decision.non_blocking_labels
    )


def test_profile_required_earnings_promotes_to_blocking() -> None:
    profile = get_balanced_research_default().model_copy(
        update={"requires_earnings_data": True}
    )
    gate = DataSufficiencyGate()
    decision = gate.evaluate_inputs(
        SufficiencyInputs(
            symbol="AMD",
            price_rows=_price_rows(60),
            stock_setup_status="SUFFICIENT",
            option_rows=_ok_option_rows(),
            earnings_rows=[],
        ),
        profile=profile,
    )
    assert decision.stock_decision_status == STOCK_DECISION_BLOCKED
    assert (
        DataSufficiencyLabel.INSUFFICIENT_EARNINGS_DATA.value
        in decision.blocking_labels
    )


def test_missing_memory_is_confidence_reducer_not_block() -> None:
    gate = DataSufficiencyGate()
    decision = gate.evaluate_inputs(
        SufficiencyInputs(
            symbol="AMD",
            price_rows=_price_rows(60),
            stock_setup_status="SUFFICIENT",
            option_rows=_ok_option_rows(),
            memory_rows=[],
        ),
        profile=get_balanced_research_default(),
    )
    assert decision.stock_decision_status == STOCK_DECISION_ALLOWED
    assert (
        DataSufficiencyLabel.INSUFFICIENT_MEMORY_DATA.value
        in decision.confidence_reducers
    )
    assert (
        DataSufficiencyLabel.INSUFFICIENT_MEMORY_DATA.value
        not in decision.blocking_labels
    )
    assert (
        DataSufficiencyLabel.INSUFFICIENT_MEMORY_DATA.value
        not in decision.non_blocking_labels
    )


def test_profile_required_memory_promotes_to_blocking() -> None:
    profile = get_balanced_research_default().model_copy(
        update={"requires_memory_data": True}
    )
    gate = DataSufficiencyGate()
    decision = gate.evaluate_inputs(
        SufficiencyInputs(
            symbol="AMD",
            price_rows=_price_rows(60),
            stock_setup_status="SUFFICIENT",
            option_rows=_ok_option_rows(),
            memory_rows=[],
        ),
        profile=profile,
    )
    assert decision.stock_decision_status == STOCK_DECISION_BLOCKED
    assert (
        DataSufficiencyLabel.INSUFFICIENT_MEMORY_DATA.value
        in decision.blocking_labels
    )


def test_decision_to_dict_shape_is_stable() -> None:
    gate = DataSufficiencyGate()
    decision = gate.evaluate_inputs(
        SufficiencyInputs(
            symbol="AMD",
            price_rows=_price_rows(60),
            stock_setup_status="SUFFICIENT",
            option_rows=_ok_option_rows(),
            news_rows=_news_rows(3),
            iv_history_rows=[
                {"snapshot_date": date(2026, 5, 1), "atm_iv_30d": 0.5}
                for _ in range(40)
            ],
            earnings_rows=[{"symbol": "AMD"}],
            memory_rows=[{"id": 1}],
        ),
    )

    payload = decision.to_dict()
    expected_keys = {
        "symbol",
        "stock_decision_status",
        "option_status",
        "blocking_labels",
        "non_blocking_labels",
        "confidence_reducers",
        "reasons",
        "actions",
        "profile_name",
        "profile_version",
        "evaluated_at",
    }
    assert expected_keys.issubset(set(payload.keys()))
    assert payload["stock_decision_status"] == STOCK_DECISION_ALLOWED
    assert payload["option_status"] == OPTION_OK


# ---------------------------------------------------------------------------
# Action builder (Phase 19 step 19.10)
# ---------------------------------------------------------------------------


def test_action_builder_emits_practical_suggestions() -> None:
    builder = InsufficientDataActionBuilder()
    actions = builder.build_actions(
        blocking_labels=[
            DataSufficiencyLabel.INSUFFICIENT_PRICE_HISTORY.value,
            DataSufficiencyLabel.INSUFFICIENT_STOCK_SETUP_DATA.value,
        ],
        non_blocking_labels=[
            DataSufficiencyLabel.OPTION_DATA_NOT_AVAILABLE.value,
            DataSufficiencyLabel.INSUFFICIENT_OPTION_DATA.value,
            DataSufficiencyLabel.INSUFFICIENT_NEWS_DATA.value,
            DataSufficiencyLabel.INSUFFICIENT_IV_DATA.value,
            DataSufficiencyLabel.INSUFFICIENT_EARNINGS_DATA.value,
        ],
        confidence_reducers=[
            DataSufficiencyLabel.INSUFFICIENT_MEMORY_DATA.value,
        ],
        option_status=OPTION_DATA_NOT_AVAILABLE,
        symbol="AMD",
    )

    by_action = {a["action"]: a for a in actions}
    assert ACTION_REFRESH_MARKET_DATA in by_action
    assert ACTION_RUN_STOCK_SETUP_DETECTION in by_action
    assert ACTION_PASTE_MANUAL_OPTION in by_action
    assert ACTION_REPASTE_MANUAL_OPTION in by_action
    assert ACTION_REFRESH_NEWS in by_action
    assert ACTION_REFRESH_IV_RISK in by_action
    assert ACTION_REFRESH_EARNINGS in by_action

    # Priorities preserve the bucket each label came from.
    assert by_action[ACTION_REFRESH_MARKET_DATA]["priority"] == "HIGH"
    assert by_action[ACTION_PASTE_MANUAL_OPTION]["priority"] == "MEDIUM"

    # Every entry carries the symbol and a non-empty description.
    for entry in actions:
        assert entry["symbol"] == "AMD"
        assert entry["description"]


def test_action_builder_is_no_op_when_all_sufficient() -> None:
    builder = InsufficientDataActionBuilder()
    actions = builder.build_actions(
        blocking_labels=[],
        non_blocking_labels=[],
        confidence_reducers=[],
        option_status=OPTION_OK,
        symbol="AMD",
    )
    assert actions == []


# ---------------------------------------------------------------------------
# DB-path and HTTP-route tests
# ---------------------------------------------------------------------------


_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_TestSession = sessionmaker(bind=_engine, autoflush=False, autocommit=False)


def _override_get_db() -> Generator[Session, None, None]:
    session = _TestSession()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(autouse=True)
def reset_db():
    app.dependency_overrides.clear()
    app.dependency_overrides[data_quality_routes.get_db] = _override_get_db
    Base.metadata.drop_all(bind=_engine)
    Base.metadata.create_all(bind=_engine)
    yield
    app.dependency_overrides.clear()


def _seed_prices(symbol: str, count: int) -> None:
    session = _TestSession()
    try:
        for i, row in enumerate(_price_rows(count)):
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


def _seed_setup(symbol: str, status: str) -> None:
    session = _TestSession()
    try:
        session.add(
            StockSetup(
                symbol=symbol,
                snapshot_date=date(2026, 5, 15),
                data_sufficiency_status=status,
                source="test",
                source_record_count=60,
                direction="LONG",
                stop_method="ATR",
            )
        )
        session.commit()
    finally:
        session.close()


def _seed_iv_history(symbol: str, count: int) -> None:
    session = _TestSession()
    try:
        for i in range(count):
            session.add(
                IvHistoryDay(
                    symbol=symbol,
                    snapshot_date=date(2026, 1, 1) + timedelta(days=i),
                    atm_iv_30d=0.5,
                    source="test",
                )
            )
        session.commit()
    finally:
        session.close()


def _seed_earnings(symbol: str) -> None:
    session = _TestSession()
    try:
        session.add(
            EarningsEvent(
                symbol=symbol,
                earnings_datetime_utc=datetime(2026, 7, 1, tzinfo=timezone.utc),
                source="test",
            )
        )
        session.commit()
    finally:
        session.close()


def test_evaluate_symbol_from_db_allows_stock_without_options() -> None:
    _seed_prices("AMD", 60)
    _seed_setup("AMD", "SUFFICIENT")
    _seed_iv_history("AMD", 40)
    _seed_earnings("AMD")

    session = _TestSession()
    try:
        gate = DataSufficiencyGate()
        decision = gate.evaluate_symbol(session, "amd")
    finally:
        session.close()

    assert decision.symbol == "AMD"
    assert decision.stock_decision_status == STOCK_DECISION_ALLOWED
    assert decision.option_status == OPTION_DATA_NOT_AVAILABLE
    assert (
        DataSufficiencyLabel.OPTION_DATA_NOT_AVAILABLE.value
        in decision.non_blocking_labels
    )


def test_evaluate_symbol_from_db_blocks_when_no_prices() -> None:
    # No prices seeded for this symbol.
    session = _TestSession()
    try:
        gate = DataSufficiencyGate()
        decision = gate.evaluate_symbol(session, "AMD")
    finally:
        session.close()

    assert decision.stock_decision_status == STOCK_DECISION_BLOCKED
    assert (
        DataSufficiencyLabel.INSUFFICIENT_PRICE_HISTORY.value
        in decision.blocking_labels
    )


def test_evaluate_symbol_normalizes_legacy_setup_label_from_db() -> None:
    _seed_prices("AMD", 60)
    _seed_setup("AMD", "INSUFFICIENT_SETUP_DATA")
    _seed_iv_history("AMD", 40)
    _seed_earnings("AMD")

    session = _TestSession()
    try:
        gate = DataSufficiencyGate()
        decision = gate.evaluate_symbol(session, "AMD")
    finally:
        session.close()

    assert decision.stock_decision_status == STOCK_DECISION_BLOCKED
    assert (
        DataSufficiencyLabel.INSUFFICIENT_STOCK_SETUP_DATA.value
        in decision.blocking_labels
    )
    assert (
        DataSufficiencyLabel.INSUFFICIENT_SETUP_DATA.value
        not in decision.blocking_labels
    )


def test_sufficiency_route_returns_stable_shape() -> None:
    _seed_prices("AMD", 60)
    _seed_setup("AMD", "SUFFICIENT")
    _seed_iv_history("AMD", 40)
    _seed_earnings("AMD")

    client = TestClient(app)
    response = client.get("/api/data-quality/sufficiency/AMD")
    assert response.status_code == 200, response.text

    body = response.json()
    assert body["status"] == "OK"
    decision = body["decision"]
    expected_keys = {
        "symbol",
        "stock_decision_status",
        "option_status",
        "blocking_labels",
        "non_blocking_labels",
        "confidence_reducers",
        "reasons",
        "actions",
        "profile_name",
        "profile_version",
        "evaluated_at",
    }
    assert expected_keys.issubset(set(decision.keys()))
    assert decision["symbol"] == "AMD"
    assert decision["stock_decision_status"] == STOCK_DECISION_ALLOWED
    assert decision["option_status"] == OPTION_DATA_NOT_AVAILABLE


def test_sufficiency_route_blocks_unknown_symbol() -> None:
    client = TestClient(app)
    response = client.get("/api/data-quality/sufficiency/ZZZ")
    assert response.status_code == 200
    decision = response.json()["decision"]
    assert decision["stock_decision_status"] == STOCK_DECISION_BLOCKED
    assert (
        DataSufficiencyLabel.INSUFFICIENT_PRICE_HISTORY.value
        in decision["blocking_labels"]
    )


def test_sufficiency_route_rejects_empty_symbol() -> None:
    client = TestClient(app)
    response = client.get("/api/data-quality/sufficiency/%20")
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# Regression: existing Phase 15 contracts must still hold
# ---------------------------------------------------------------------------


def test_phase15_no_option_path_unchanged_through_the_gate() -> None:
    """The Phase 15 ``OPTION_DATA_NOT_AVAILABLE`` non-blocking contract
    must still hold when reached via the Phase 19 gate."""
    gate = DataSufficiencyGate()
    decision = gate.evaluate_inputs(
        SufficiencyInputs(
            symbol="AMD",
            price_rows=_price_rows(60),
            stock_setup_status="SUFFICIENT",
            option_rows=None,
            option_data_requested=False,
        ),
    )
    assert decision.option_status == OPTION_DATA_NOT_AVAILABLE
    assert decision.stock_decision_status == STOCK_DECISION_ALLOWED
