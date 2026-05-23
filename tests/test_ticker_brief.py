"""Phase 28, step 28.16 — One-Page Ticker Brief tests.

Covers the pure section builders (especially the explicit option empty state)
and the end-to-end service / route assembly. The brief must show absent data
honestly and never invent missing option values.
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.main import app
from app.brief.brief_sections import (
    OPTION_DATA_NOT_AVAILABLE,
    build_earnings_iv_section,
    build_option_expression_section,
)
from app.brief.ticker_brief_builder import BriefInputs, build_ticker_brief
from app.brief.ticker_brief_service import TickerBriefService
from app.database.base import Base
from app.database.connection import get_db_session
from app.quant.stock_setup_models import StockSetup

_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_TestSession = sessionmaker(bind=_engine, autoflush=False, autocommit=False)
TODAY = date(2026, 5, 20)


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


def _seed_setup(symbol: str, **overrides) -> None:
    session = _TestSession()
    defaults = dict(
        symbol=symbol,
        snapshot_date=TODAY,
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


# ---------------------------------------------------------------------------
# Pure section builder tests
# ---------------------------------------------------------------------------


def test_option_section_explicit_empty_state() -> None:
    section = build_option_expression_section(
        option_expression={"expression_label": "OPTION_EXPR_NOT_EVALUATED"},
        has_manual_snapshot=False,
        option_contract_criteria=None,
    )
    assert section["available"] is False
    assert section["option_expression_status"] == OPTION_DATA_NOT_AVAILABLE
    assert section["has_manual_option_snapshot"] is False
    assert "without option contract analysis" in section["detail"]


def test_option_section_available_when_snapshot_and_evaluated() -> None:
    section = build_option_expression_section(
        option_expression={
            "expression_label": "OPTION_EXPR_OK",
            "blocking_labels": [],
            "rationale": ["passes filters"],
        },
        has_manual_snapshot=True,
        option_contract_criteria={"dte_min": 45},
    )
    assert section["available"] is True
    assert section["option_expression_status"] == "OPTION_EXPR_OK"


def test_earnings_iv_section_reports_missing_iv_as_unavailable() -> None:
    section = build_earnings_iv_section(earnings=None, iv=None)
    assert section["iv"]["available"] is False
    assert "unavailable, not low" in section["iv"]["detail"]


def test_builder_assembles_all_sections() -> None:
    inputs = BriefInputs(
        symbol="AMD",
        snapshot_date=TODAY,
        final_action_label="READY_TO_RESEARCH_STOCK_ONLY",
        suggested_action_summary="Research AMD now.",
        stock_thesis={"thesis_label": "THESIS_READY_TO_RESEARCH", "rationale": []},
        option_expression={"expression_label": "OPTION_EXPR_NOT_EVALUATED"},
        version_stamp={"rule_version": "x"},
        confidence_breakdown={"total": 70.0},
    )
    brief = build_ticker_brief(inputs)
    section_names = [s["section"] for s in brief.sections]
    assert section_names == [
        "current_action",
        "stock_thesis",
        "option_expression",
        "manual_option_reminder",
        "earnings_iv",
        "news_events",
        "memory_similar_cases",
        "decision_trace",
        "confidence_breakdown",
        "version_stamp",
    ]
    assert brief.option_expression_status == OPTION_DATA_NOT_AVAILABLE


# ---------------------------------------------------------------------------
# Service / route tests
# ---------------------------------------------------------------------------


def test_service_builds_brief_stock_only() -> None:
    _seed_setup("AMD")
    session = _TestSession()
    try:
        evaluation = TickerBriefService().build_brief(session, "AMD", persist=True)
    finally:
        session.close()
    brief = evaluation.brief
    assert brief.symbol == "AMD"
    # Option side is honestly absent for a stock-only brief.
    option = next(s for s in brief.sections if s["section"] == "option_expression")
    assert option["available"] is False
    assert option["option_expression_status"] == OPTION_DATA_NOT_AVAILABLE
    assert evaluation.record is not None


def test_brief_route_returns_sections() -> None:
    _seed_setup("NVDA")
    client = TestClient(app)
    response = client.get("/api/ticker-brief/NVDA")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "OK"
    assert body["brief"]["symbol"] == "NVDA"
    assert len(body["brief"]["sections"]) == 10


def test_brief_route_rejects_blank_symbol() -> None:
    client = TestClient(app)
    response = client.get("/api/ticker-brief/%20")
    assert response.status_code == 400
