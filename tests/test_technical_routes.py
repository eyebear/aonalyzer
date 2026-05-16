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
from app.quant.technical_snapshot_models import TechnicalSnapshot


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
        session.add_all(
            [
                TechnicalSnapshot(
                    symbol="AMD",
                    snapshot_date=today,
                    source="daily_prices",
                    source_record_count=220,
                    last_close=120.0,
                    last_volume=1_000_000.0,
                    sma_20=118.0,
                    sma_50=115.0,
                    sma_200=110.0,
                    ema_12=119.0,
                    ema_26=117.0,
                    rsi_14=55.5,
                    macd=2.0,
                    macd_signal=1.5,
                    macd_histogram=0.5,
                    atr_14=2.0,
                    bollinger_upper=122.0,
                    bollinger_middle=118.0,
                    bollinger_lower=114.0,
                    volume_ratio_20=1.25,
                    data_sufficiency_status="SUFFICIENT",
                    insufficient_indicators_json=[],
                ),
                TechnicalSnapshot(
                    symbol="AMD",
                    snapshot_date=today - timedelta(days=1),
                    source="daily_prices",
                    source_record_count=219,
                    last_close=119.5,
                    last_volume=950_000.0,
                    sma_20=117.5,
                    sma_50=114.8,
                    sma_200=109.8,
                    ema_12=118.7,
                    ema_26=116.7,
                    rsi_14=54.0,
                    macd=1.8,
                    macd_signal=1.4,
                    macd_histogram=0.4,
                    atr_14=2.1,
                    bollinger_upper=121.5,
                    bollinger_middle=117.5,
                    bollinger_lower=113.5,
                    volume_ratio_20=1.18,
                    data_sufficiency_status="SUFFICIENT",
                    insufficient_indicators_json=[],
                ),
                TechnicalSnapshot(
                    symbol="NEW",
                    snapshot_date=today,
                    source="daily_prices",
                    source_record_count=10,
                    last_close=20.0,
                    last_volume=500_000.0,
                    sma_20=None,
                    sma_50=None,
                    sma_200=None,
                    ema_12=None,
                    ema_26=None,
                    rsi_14=None,
                    macd=None,
                    macd_signal=None,
                    macd_histogram=None,
                    atr_14=None,
                    bollinger_upper=None,
                    bollinger_middle=None,
                    bollinger_lower=None,
                    volume_ratio_20=None,
                    data_sufficiency_status="INSUFFICIENT_PRICE_HISTORY",
                    insufficient_indicators_json=["sma_20", "sma_50", "sma_200"],
                ),
            ]
        )
        session.commit()
    finally:
        session.close()

    yield

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


client = TestClient(app)


def test_list_snapshots_returns_all_with_indicators() -> None:
    response = client.get("/api/technical/snapshots")
    assert response.status_code == 200

    body = response.json()
    assert body["status"] == "OK"
    assert body["count"] == 3
    for snap in body["snapshots"]:
        assert "indicators" in snap
        assert "sma_20" in snap["indicators"]
        assert "rsi_14" in snap["indicators"]
        assert "data_sufficiency_status" in snap
        assert "insufficient_indicators" in snap


def test_list_snapshots_filter_by_symbol() -> None:
    response = client.get("/api/technical/snapshots?symbol=AMD")
    assert response.status_code == 200

    body = response.json()
    assert body["count"] == 2
    assert {s["symbol"] for s in body["snapshots"]} == {"AMD"}


def test_list_snapshots_filter_by_since() -> None:
    response = client.get("/api/technical/snapshots?since=2026-05-14")
    assert response.status_code == 200

    body = response.json()
    # both AMD-today and NEW-today match
    assert body["count"] == 2


def test_latest_snapshot_for_known_symbol() -> None:
    response = client.get("/api/technical/snapshots/latest?symbol=AMD")
    assert response.status_code == 200

    body = response.json()
    assert body["status"] == "OK"
    assert body["symbol"] == "AMD"
    assert body["snapshot"] is not None
    assert body["snapshot"]["snapshot_date"] == "2026-05-14"
    assert body["snapshot"]["indicators"]["rsi_14"] == 55.5
    assert body["data_sufficiency_status"] == "SUFFICIENT"


def test_latest_snapshot_for_unknown_symbol_returns_clean_empty() -> None:
    response = client.get("/api/technical/snapshots/latest?symbol=ZZZZ")
    assert response.status_code == 200

    body = response.json()
    assert body["snapshot"] is None
    assert body["data_sufficiency_status"] == "INSUFFICIENT_PRICE_HISTORY"


def test_latest_snapshot_reports_insufficient_status_when_appropriate() -> None:
    response = client.get("/api/technical/snapshots/latest?symbol=NEW")
    assert response.status_code == 200

    body = response.json()
    assert body["data_sufficiency_status"] == "INSUFFICIENT_PRICE_HISTORY"
    assert body["snapshot"] is not None
    assert "sma_20" in body["snapshot"]["insufficient_indicators"]


def test_ticker_technical_snapshots_route() -> None:
    response = client.get("/api/tickers/AMD/technical-snapshots")
    assert response.status_code == 200

    body = response.json()
    assert body["status"] == "OK"
    assert body["symbol"] == "AMD"
    assert body["count"] == 2
    assert body["snapshots"][0]["snapshot_date"] == "2026-05-14"


def test_technical_api_works_with_no_option_data() -> None:
    """Sanity: nothing in technical responses references option data."""
    response = client.get("/api/technical/snapshots")
    assert response.status_code == 200

    body = response.json()
    for snap in body["snapshots"]:
        keys = set(snap.keys()) | set(snap["indicators"].keys())
        assert "option" not in {k.lower() for k in keys}
        assert "manual_option" not in {k.lower() for k in keys}
