from collections.abc import Generator
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.main import app
from app.database.base import Base
from app.database.connection import get_db_session
from app.setup_detection.setup_detection_models import StockSetupSignal

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
    yield
    app.dependency_overrides.clear()


def _seed_signal(symbol="AMD", setup_type="PULLBACK_LONG", snapshot_date=date(2026, 5, 15)) -> None:
    session = TestingSessionLocal()
    try:
        session.add(
            StockSetupSignal(
                symbol=symbol,
                snapshot_date=snapshot_date,
                setup_type=setup_type,
                direction="LONG",
                score=85,
                close=104.0,
                rsi_14=45.0,
                risk_reward=3.0,
                regime_label="RISK_ON",
                data_sufficiency_status="SUFFICIENT",
                reasons_json=["pullback"],
                components_json={"base": 50},
            )
        )
        session.commit()
    finally:
        session.close()


def test_latest_returns_clean_state_when_empty() -> None:
    client = TestClient(app)
    response = client.get("/api/setup-signals/latest", params={"symbol": "AMD"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "OK"
    assert body["signal"] is None
    assert body["data_sufficiency_status"] == "INSUFFICIENT_INPUT"


def test_latest_returns_signal() -> None:
    _seed_signal()
    client = TestClient(app)
    response = client.get("/api/setup-signals/latest", params={"symbol": "AMD"})
    body = response.json()
    assert body["data_sufficiency_status"] == "SUFFICIENT"
    assert body["signal"]["setup_type"] == "PULLBACK_LONG"
    assert body["signal"]["direction"] == "LONG"
    assert body["signal"]["score"] == 85


def test_list_filters_by_setup_type() -> None:
    _seed_signal(symbol="AMD", setup_type="PULLBACK_LONG")
    _seed_signal(symbol="TSLA", setup_type="NO_TRADE")
    client = TestClient(app)

    response = client.get("/api/setup-signals", params={"setup_type": "PULLBACK_LONG"})
    body = response.json()
    assert body["status"] == "OK"
    assert body["count"] == 1
    assert body["signals"][0]["symbol"] == "AMD"
