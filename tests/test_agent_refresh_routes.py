import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.main import app
from app.database.base import Base
from app.database.connection import get_db_session

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

    yield

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


client = TestClient(app)


def test_manual_test_refresh_creates_agent_run() -> None:
    response = client.post("/api/agent/refresh/test")

    assert response.status_code == 200

    body = response.json()

    assert body["job_name"] == "test_refresh"
    assert body["job_type"] == "TEST"
    assert body["status"] == "SUCCESS"
    assert body["triggered_by"] == "USER"
    assert body["trigger_source"] == "API"


def test_agent_status_after_manual_refresh() -> None:
    client.post("/api/agent/refresh/test")

    response = client.get("/api/agent/status")

    assert response.status_code == 200

    body = response.json()

    assert body["status"] == "has_runs"
    assert body["latest_job_name"] == "test_refresh"
    assert body["latest_job_status"] == "SUCCESS"


def test_agent_runs_after_manual_refresh() -> None:
    client.post("/api/agent/refresh/test")

    response = client.get("/api/agent/runs")

    assert response.status_code == 200

    body = response.json()

    assert body["count"] == 1
    assert body["runs"][0]["job_name"] == "test_refresh"


def test_manual_refresh_endpoints_exist() -> None:
    endpoints = [
        "/api/agent/refresh/all",
        "/api/agent/refresh/market-data",
        "/api/agent/refresh/options",
        "/api/agent/refresh/news",
        "/api/agent/refresh/filings",
        "/api/agent/refresh/earnings",
        "/api/agent/refresh/iv-risk",
        "/api/agent/run/recommendations",
    ]

    for endpoint in endpoints:
        response = client.post(endpoint)
        assert response.status_code == 200

        body = response.json()

        assert body["status"] == "SUCCESS"
        assert body["triggered_by"] == "USER"
        assert body["trigger_source"] == "API"


def test_ticker_manual_refresh_endpoints_exist() -> None:
    endpoints = [
        "/api/tickers/AMD/refresh/market-data",
        "/api/tickers/AMD/refresh/options",
        "/api/tickers/AMD/refresh/news",
        "/api/tickers/AMD/analyze",
    ]

    for endpoint in endpoints:
        response = client.post(endpoint)
        assert response.status_code == 200

        body = response.json()

        assert body["status"] == "SUCCESS"
        assert body["triggered_by"] == "USER"
        assert body["trigger_source"] == "API"
        assert body["symbols_processed"] == 1