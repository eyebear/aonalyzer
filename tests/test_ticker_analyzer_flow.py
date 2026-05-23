"""Phase 33, step 33.18 — ticker analyzer route + manual option flow tests.

Validates the route-level integration the Ticker Analyzer page composes:

* stock-only analysis works without any option data (never blocked);
* pasting a manual option contract enables the option-aware path
  (suitability runs, brief reflects the snapshot);
* malformed / empty option text degrades safely.

This protects the core non-blocking option-data contract end-to-end.
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
from app.database.base import Base
from app.database.connection import get_db_session
from app.database.models import DailyPrice
from app.quant.stock_setup_models import StockSetup

_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_TestSession = sessionmaker(bind=_engine, autoflush=False, autocommit=False)
TODAY = date(2026, 5, 20)

FULL_OPTION_TEXT = (
    "AMD June 19 2026 170 call, stock around 165.20, "
    "bid 8.20 ask 8.80, last 8.50, IV around 42.5%, "
    "delta .48, gamma .025, theta -.09, vega .31, "
    "volume 1200, OI 5400."
)


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


def _seed_prices(symbol: str, n: int = 80) -> None:
    base = date(2026, 1, 2)
    session = _TestSession()
    try:
        for i in range(n):
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
        session.commit()
    finally:
        session.close()


def _seed_setup(symbol: str) -> None:
    _seed_prices(symbol)
    session = _TestSession()
    try:
        session.add(
            StockSetup(
                symbol=symbol,
                snapshot_date=TODAY,
                source="test",
                source_record_count=60,
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


def test_stock_only_path_never_blocked_by_missing_option() -> None:
    _seed_setup("AMD")
    client = TestClient(app)

    brief = client.get("/api/ticker-brief/AMD")
    assert brief.status_code == 200
    option_section = next(
        s for s in brief.json()["brief"]["sections"] if s["section"] == "option_expression"
    )
    assert option_section["available"] is False
    assert option_section["option_expression_status"] == "OPTION_DATA_NOT_AVAILABLE"

    action = client.get("/api/action-suggestions/AMD")
    assert action.status_code == 200
    # Stock thesis must still produce a non-blocked label.
    assert action.json()["package"]["final_action_label"] != "INSUFFICIENT_PRICE_HISTORY"


def test_manual_option_paste_enables_option_aware_path() -> None:
    _seed_setup("AMD")
    client = TestClient(app)

    parsed = client.post(
        "/api/tickers/AMD/options/manual-input", json={"raw_text": FULL_OPTION_TEXT}
    )
    assert parsed.status_code == 200
    snapshot = parsed.json()["snapshot"]
    sid = snapshot["id"]
    assert snapshot["strike"] == 170.0
    assert snapshot["breakeven"] == 178.5

    suit = client.post(f"/api/option-suitability/snapshots/{sid}/evaluate")
    assert suit.status_code == 200

    # Brief with the snapshot now treats the option side as evaluated.
    brief = client.get(
        "/api/ticker-brief/AMD", params={"manual_option_snapshot_id": sid}
    )
    assert brief.status_code == 200
    option_section = next(
        s for s in brief.json()["brief"]["sections"] if s["section"] == "option_expression"
    )
    assert option_section["has_manual_option_snapshot"] is True


def test_empty_option_text_degrades_safely() -> None:
    _seed_setup("AMD")
    client = TestClient(app)
    # Empty raw_text is rejected by request validation (min_length=1), not a crash.
    response = client.post(
        "/api/tickers/AMD/options/manual-input", json={"raw_text": ""}
    )
    assert response.status_code == 422


def test_vague_option_text_parses_without_inventing_values() -> None:
    _seed_setup("AMD")
    client = TestClient(app)
    response = client.post(
        "/api/tickers/AMD/options/manual-input",
        json={"raw_text": "I am looking at an AMD option but have no chain data yet."},
    )
    assert response.status_code == 200
    snapshot = response.json()["snapshot"]
    # No values invented: strike/bid/ask stay None.
    assert snapshot["strike"] is None
    assert snapshot["bid"] is None
