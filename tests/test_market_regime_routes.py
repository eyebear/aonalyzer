from collections.abc import Generator
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.main import app
from app.core.config import AppSettings
from app.database.base import Base
from app.database.connection import get_db_session
from app.database.models import DailyPrice
from app.market_regime.market_regime_service import MarketRegimeService

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


def _settings() -> AppSettings:
    return AppSettings(
        market_regime_sector_etfs=["XLK", "XLF"],
        market_regime_benchmark_symbols=["SPY"],
        market_regime_trend_fast_period=2,
        market_regime_trend_slow_period=3,
        market_regime_rs_lookback_days=2,
        market_regime_min_price_rows=3,
    )


def _seed_closes(db, symbol: str, closes: list[float], end_date: date = date(2026, 5, 15)) -> None:
    start = end_date - timedelta(days=len(closes) - 1)
    for index, close in enumerate(closes):
        db.add(
            DailyPrice(
                symbol=symbol.upper(),
                price_date=start + timedelta(days=index),
                open_price=close,
                high_price=close,
                low_price=close,
                close_price=close,
                adjusted_close_price=close,
                volume=100_000,
                source="test",
            )
        )
    db.commit()


@pytest.fixture(autouse=True)
def reset_test_database():
    app.dependency_overrides.clear()
    app.dependency_overrides[get_db_session] = override_get_db_session

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    yield

    app.dependency_overrides.clear()


def _populate() -> None:
    session = TestingSessionLocal()
    try:
        _seed_closes(session, "SPY", [100.0, 101.0, 102.0, 103.0, 104.0, 105.0])
        _seed_closes(session, "QQQ", [200.0, 202.0, 204.0, 206.0, 208.0, 210.0])
        _seed_closes(session, "IWM", [50.0, 51.0, 52.0, 53.0, 54.0, 55.0])
        _seed_closes(session, "^VIX", [12.0, 12.0, 12.0])
        _seed_closes(session, "^TNX", [4.0, 4.0, 4.0])
        _seed_closes(session, "XLK", [100.0, 110.0, 121.0])
        _seed_closes(session, "XLF", [100.0, 100.0, 100.0])
        MarketRegimeService(settings=_settings()).refresh_market_regime(db=session)
    finally:
        session.close()


def test_latest_returns_clean_state_when_empty() -> None:
    client = TestClient(app)
    response = client.get("/api/market-regime/latest")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "OK"
    assert body["regime"] is None
    assert body["data_sufficiency_status"] == "INSUFFICIENT_PRICE_HISTORY"


def test_latest_returns_regime_after_refresh() -> None:
    _populate()
    client = TestClient(app)
    response = client.get("/api/market-regime/latest")
    assert response.status_code == 200
    body = response.json()
    assert body["data_sufficiency_status"] == "SUFFICIENT"
    assert body["regime"]["regime"]["label"] == "RISK_ON"
    assert body["regime"]["vix"]["state"] == "CALM"


def test_list_endpoint_returns_snapshots() -> None:
    _populate()
    client = TestClient(app)
    response = client.get("/api/market-regime")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "OK"
    assert body["count"] == 1
    assert body["regimes"][0]["regime"]["label"] == "RISK_ON"


def test_sectors_endpoint_returns_ranked_sectors() -> None:
    _populate()
    client = TestClient(app)
    response = client.get("/api/market-regime/sectors")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "OK"
    assert body["count"] == 2
    ranks = {s["sector_symbol"]: s["rs_rank"] for s in body["sectors"]}
    assert ranks["XLK"] == 1
    assert ranks["XLF"] == 2
    # sectors are ordered by rs_rank ascending
    assert [s["sector_symbol"] for s in body["sectors"]] == ["XLK", "XLF"]
