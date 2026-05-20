from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.main import app
from app.database.base import Base
from app.database.connection import get_db_session
from app.database.models import AgentRun, Ticker, Watchlist

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

TestingSessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
)


def override_get_db_session():
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
        aapl = Ticker(
            symbol="AAPL",
            name="Apple Inc.",
            market="US",
            asset_type="STOCK",
            currency="USD",
            exchange="NASDAQ",
            is_active=True,
        )

        spy = Ticker(
            symbol="SPY",
            name="SPDR S&P 500 ETF Trust",
            market="US",
            asset_type="ETF",
            currency="USD",
            exchange="NYSEARCA",
            is_active=True,
        )

        session.add_all([aapl, spy])
        session.flush()

        session.add_all(
            [
                Watchlist(ticker_id=aapl.id, watchlist_name="Default", is_active=True),
                Watchlist(ticker_id=spy.id, watchlist_name="Default", is_active=True),
            ]
        )

        session.add(
            AgentRun(
                job_name="test_job",
                job_type="TEST",
                status="SUCCESS",
                started_at=datetime.now(timezone.utc),
                finished_at=datetime.now(timezone.utc),
                duration_seconds=1.5,
                triggered_by="SYSTEM",
                trigger_source="TEST",
                symbols_processed=2,
                records_created=2,
                records_updated=0,
                records_failed=0,
                error_message=None,
            )
        )

        session.commit()
    finally:
        session.close()

    yield

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


client = TestClient(app)


def test_health_endpoint_works() -> None:
    response = client.get("/health")

    assert response.status_code == 200

    body = response.json()

    assert body["status"] == "ok"
    assert body["app_name"] == "Aonalyzer"
    assert body["technical_name"] == "aonalyzer"


def test_system_status_endpoint_works() -> None:
    response = client.get("/api/system/status")

    assert response.status_code == 200

    body = response.json()

    assert body["status"] == "running"
    assert body["app_name"] == "Aonalyzer"
    assert body["technical_name"] == "aonalyzer"
    assert body["default_strategy_profile"] == "Balanced Research Default"


def test_tickers_endpoint_returns_watchlist_symbols() -> None:
    response = client.get("/api/tickers")

    assert response.status_code == 200

    body = response.json()
    symbols = {ticker["symbol"] for ticker in body["tickers"]}

    assert body["count"] == 2
    assert "AAPL" in symbols
    assert "SPY" in symbols


def test_active_profile_endpoint_works() -> None:
    response = client.get("/api/settings/profile")

    assert response.status_code == 200

    body = response.json()

    assert body["active_profile_name"] == "Balanced Research Default"
    assert body["active_profile_version"] == "balanced_research_default_1.0"


def test_save_profile_endpoint_rejects_hard_filter_bypass() -> None:
    active_profile_response = client.get("/api/settings/profile")
    payload = active_profile_response.json()["profile"]

    payload["profile_name"] = "Bad Custom"
    payload["profile_type"] = "CUSTOM"
    payload["profile_version"] = "bad_custom_1.0"
    payload["hard_filters_can_be_bypassed"] = True

    response = client.post("/api/settings/profile", json=payload)

    assert response.status_code == 422


def test_agent_status_endpoint_works() -> None:
    response = client.get("/api/agent/status")

    assert response.status_code == 200

    body = response.json()

    assert body["status"] == "has_runs"
    assert body["latest_job_name"] == "test_job"
    assert body["latest_job_status"] == "SUCCESS"


def test_agent_runs_endpoint_works() -> None:
    response = client.get("/api/agent/runs")

    assert response.status_code == 200

    body = response.json()

    assert body["count"] == 1
    assert body["runs"][0]["job_name"] == "test_job"