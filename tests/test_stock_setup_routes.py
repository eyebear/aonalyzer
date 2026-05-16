from collections.abc import Generator
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.main import app
from app.database.base import Base
from app.database.connection import get_db_session
from app.quant.stock_setup_models import StockSetup


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def override_get_db_session() -> Generator[Session, None, None]:
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(autouse=True)
def reset_test_database():
    app.dependency_overrides.clear()
    app.dependency_overrides[get_db_session] = override_get_db_session

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    session = TestingSessionLocal()
    try:
        today = date(2026, 5, 14)
        session.add(
            StockSetup(
                symbol="AMD",
                snapshot_date=today,
                source="daily_prices+technical",
                source_record_count=120,
                current_close=100.0,
                nearest_support=95.0,
                nearest_resistance=110.0,
                swing_low=95.0,
                swing_high=110.0,
                sma_20=99.0,
                sma_50=98.0,
                sma_200=92.0,
                atr_14=2.0,
                direction="LONG",
                entry_zone_low=99.0,
                entry_zone_high=101.0,
                target_price=110.0,
                stop_price=97.0,
                stop_method="ATR_1_5X",
                risk_per_share=3.0,
                reward_per_share=10.0,
                stock_risk_reward=10.0 / 3.0,
                data_sufficiency_status="SUFFICIENT",
                insufficient_reasons_json=[],
            )
        )
        session.add(
            StockSetup(
                symbol="AMD",
                snapshot_date=today - timedelta(days=1),
                source="daily_prices+technical",
                source_record_count=119,
                current_close=99.5,
                nearest_support=94.5,
                nearest_resistance=109.5,
                swing_low=94.5,
                swing_high=109.5,
                sma_20=98.5,
                sma_50=97.5,
                sma_200=91.5,
                atr_14=2.1,
                direction="LONG",
                entry_zone_low=98.45,
                entry_zone_high=100.55,
                target_price=109.5,
                stop_price=96.35,
                stop_method="ATR_1_5X",
                risk_per_share=3.15,
                reward_per_share=10.0,
                stock_risk_reward=10.0 / 3.15,
                data_sufficiency_status="SUFFICIENT",
                insufficient_reasons_json=[],
            )
        )
        session.add(
            StockSetup(
                symbol="NEW",
                snapshot_date=today,
                source="daily_prices+technical",
                source_record_count=2,
                current_close=None,
                nearest_support=None,
                nearest_resistance=None,
                swing_low=None,
                swing_high=None,
                sma_20=None,
                sma_50=None,
                sma_200=None,
                atr_14=None,
                direction="UNDEFINED",
                entry_zone_low=None,
                entry_zone_high=None,
                target_price=None,
                stop_price=None,
                stop_method="UNDEFINED",
                risk_per_share=None,
                reward_per_share=None,
                stock_risk_reward=None,
                data_sufficiency_status="INSUFFICIENT_PRICE_HISTORY",
                insufficient_reasons_json=["Need at least 5 daily price rows; found 2."],
            )
        )
        session.commit()
    finally:
        session.close()

    yield

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


client = TestClient(app)


def test_list_setups_returns_all_with_levels_and_setup_blocks() -> None:
    response = client.get("/api/setups")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 3
    for s in body["setups"]:
        assert "levels" in s
        assert "setup" in s
        assert "cached_indicators" in s
        assert "data_sufficiency_status" in s


def test_list_setups_filter_by_symbol() -> None:
    response = client.get("/api/setups?symbol=AMD")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 2
    assert {s["symbol"] for s in body["setups"]} == {"AMD"}


def test_list_setups_filter_by_since() -> None:
    response = client.get("/api/setups?since=2026-05-14")
    assert response.status_code == 200
    body = response.json()
    # both AMD-today and NEW-today match
    assert body["count"] == 2


def test_latest_setup_for_known_symbol() -> None:
    response = client.get("/api/setups/latest?symbol=AMD")
    assert response.status_code == 200
    body = response.json()
    assert body["setup"] is not None
    assert body["setup"]["snapshot_date"] == "2026-05-14"
    assert body["setup"]["setup"]["stop_price"] == 97.0
    assert body["setup"]["levels"]["nearest_support"] == 95.0
    assert body["data_sufficiency_status"] == "SUFFICIENT"


def test_latest_setup_for_unknown_symbol_returns_clean_empty() -> None:
    response = client.get("/api/setups/latest?symbol=ZZZZ")
    assert response.status_code == 200
    body = response.json()
    assert body["setup"] is None
    assert body["data_sufficiency_status"] == "INSUFFICIENT_PRICE_HISTORY"


def test_latest_setup_for_insufficient_symbol_reports_correctly() -> None:
    response = client.get("/api/setups/latest?symbol=NEW")
    assert response.status_code == 200
    body = response.json()
    assert body["data_sufficiency_status"] == "INSUFFICIENT_PRICE_HISTORY"
    assert body["setup"]["setup"]["direction"] == "UNDEFINED"
    assert body["setup"]["setup"]["stop_method"] == "UNDEFINED"
    assert len(body["setup"]["insufficient_reasons"]) >= 1


def test_ticker_stock_setup_route() -> None:
    response = client.get("/api/tickers/AMD/stock-setup")
    assert response.status_code == 200
    body = response.json()
    assert body["symbol"] == "AMD"
    assert body["setup"]["target_price"] == 110.0
    assert body["setup"]["direction"] == "LONG"


def test_setup_api_works_with_no_option_data() -> None:
    """Sanity — Phase 12 responses must not reference manual option data."""
    response = client.get("/api/setups")
    assert response.status_code == 200
    body = response.json()
    for s in body["setups"]:
        all_keys = set(s.keys()) | set(s.get("setup", {}).keys()) | set(s.get("levels", {}).keys())
        for key in all_keys:
            assert "option" not in key.lower()
            assert "manual" not in key.lower()
