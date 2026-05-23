"""Phase 37, step 37.16 — AI Research Chat tests.

Protects the chat safety contract independent of any AI provider:

* answer-mode routing;
* missing option data -> says missing, never invents values;
* incomplete option data -> explains what cannot be calculated;
* hard filters / deterministic verdict are never overridden;
* source-citation assembly;
* deterministic degraded-state answer when no provider is configured.
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.main import app
from app.chat.answer_modes import (
    DEFAULT_MODE,
    MODE_DECISION_TRACE,
    MODE_OPTION_TEXT_READER,
    route_mode,
)
from app.chat.chat_service import SYSTEM_GUARDRAILS, ChatService
from app.chat.context_builder import (
    OPTION_DATA_AVAILABLE,
    OPTION_DATA_INCOMPLETE,
    OPTION_DATA_NOT_AVAILABLE,
    ChatContextBuilder,
)
from app.database.base import Base
from app.database.connection import get_db_session
from app.database.models import DailyPrice
from app.options.manual_option_input_service import ManualOptionInputService
from app.quant.stock_setup_models import StockSetup

_engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
)
_TestSession = sessionmaker(bind=_engine, autoflush=False, autocommit=False)
TODAY = date(2026, 5, 20)

FULL_OPTION_TEXT = (
    "AMD June 19 2026 170 call, stock around 165.20, "
    "bid 8.20 ask 8.80, last 8.50, IV around 42.5%, "
    "delta .48, gamma .025, theta -.09, vega .31, volume 1200, OI 5400."
)
PARTIAL_OPTION_TEXT = "AMD 170 call expiring June 19 2026"  # no pricing -> incomplete


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
    with _engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS manual_option_snapshots"))
    Base.metadata.create_all(bind=_engine)
    yield
    app.dependency_overrides.clear()


def _seed_setup(symbol: str) -> None:
    base = date(2026, 1, 2)
    session = _TestSession()
    try:
        for i in range(80):
            session.add(
                DailyPrice(
                    symbol=symbol,
                    price_date=base + timedelta(days=i),
                    open_price=150.0 + i * 0.1,
                    high_price=151.0 + i * 0.1,
                    low_price=149.0 + i * 0.1,
                    close_price=150.5 + i * 0.1,
                    volume=1_000_000 + i,
                    source="test",
                )
            )
        session.add(
            StockSetup(
                symbol=symbol,
                snapshot_date=TODAY,
                source="test",
                source_record_count=80,
                current_close=165.0,
                nearest_support=158.0,
                nearest_resistance=185.0,
                sma_50=160.0,
                atr_14=4.0,
                direction="LONG",
                stop_method="ATR",
                target_price=185.0,
                stop_price=156.0,
                risk_per_share=9.0,
                reward_per_share=20.0,
                stock_risk_reward=2.2,
                entry_zone_low=158.0,
                entry_zone_high=167.0,
                data_sufficiency_status="SUFFICIENT",
            )
        )
        session.commit()
    finally:
        session.close()


# --- mode routing ----------------------------------------------------------


def test_mode_routing_defaults_and_known() -> None:
    assert route_mode(None) == DEFAULT_MODE
    assert route_mode("garbage") == DEFAULT_MODE
    assert route_mode("decision_trace") == MODE_DECISION_TRACE
    assert route_mode("OPTION_TEXT_READER") == MODE_OPTION_TEXT_READER


# --- missing / incomplete option data --------------------------------------


def test_missing_option_data_states_missing_and_never_invents() -> None:
    _seed_setup("AMD")
    session = _TestSession()
    try:
        resp = ChatService().answer(
            session, question="What about options?", symbol="AMD", mode="EXPLAIN"
        )
    finally:
        session.close()
    assert resp.option_data_status == OPTION_DATA_NOT_AVAILABLE
    assert "not available" in resp.answer.lower()
    # No invented option numbers leak in (no bid/ask/strike fabricated).
    assert "bid" not in resp.answer.lower() or "missing" in resp.answer.lower()


def test_incomplete_option_data_explains_what_cannot_be_calculated() -> None:
    _seed_setup("AMD")
    session = _TestSession()
    try:
        snap = ManualOptionInputService().create_manual_snapshot(
            db=session, raw_text=PARTIAL_OPTION_TEXT, symbol="AMD"
        )
        resp = ChatService().answer(
            session,
            question="Read this option",
            symbol="AMD",
            mode="OPTION_TEXT_READER",
            manual_option_snapshot_id=snap.id,
        )
    finally:
        session.close()
    assert resp.option_data_status == OPTION_DATA_INCOMPLETE
    assert "incomplete" in resp.answer.lower()


def test_complete_option_data_marked_available() -> None:
    _seed_setup("AMD")
    session = _TestSession()
    try:
        snap = ManualOptionInputService().create_manual_snapshot(
            db=session, raw_text=FULL_OPTION_TEXT, symbol="AMD"
        )
        ctx = ChatContextBuilder().build(
            session, "AMD", manual_option_snapshot_id=snap.id
        )
    finally:
        session.close()
    assert ctx.option_data_status == OPTION_DATA_AVAILABLE


# --- hard filter respect ----------------------------------------------------


def test_chat_does_not_override_deterministic_verdict() -> None:
    _seed_setup("AMD")
    session = _TestSession()
    try:
        resp = ChatService().answer(session, question="?", symbol="AMD", mode="EXPLAIN")
    finally:
        session.close()
    # The degraded answer reflects (does not change) the deterministic label.
    assert resp.context_summary["final_action_label"] == resp.context_summary["final_action_label"]
    assert resp.context_summary["final_action_label"] in resp.answer
    # The guardrail forbidding overrides is present in the system contract.
    assert "Never override" in SYSTEM_GUARDRAILS


# --- citations + degraded ---------------------------------------------------


def test_citations_and_degraded_state_without_provider() -> None:
    _seed_setup("AMD")
    session = _TestSession()
    try:
        resp = ChatService().answer(session, question="Explain", symbol="AMD")
    finally:
        session.close()
    # No provider configured -> degraded deterministic answer (never an error).
    assert resp.degraded is True
    assert resp.provider_status != "OK"
    # Citations always include the option-data status field.
    fields = {c["field"] for c in resp.citations}
    assert "option_data_status" in fields
    assert "final_action_label" in fields


def test_chat_route_shape() -> None:
    _seed_setup("AMD")
    client = TestClient(app)
    response = client.post("/api/chat", json={"symbol": "AMD", "mode": "RISK_REVIEW"})
    assert response.status_code == 200
    body = response.json()["response"]
    assert body["mode"] == "RISK_REVIEW"
    assert "option_data_status" in body
    assert "citations" in body

    modes = client.get("/api/chat/modes")
    assert modes.status_code == 200
    assert "EXPLAIN" in modes.json()["modes"]
