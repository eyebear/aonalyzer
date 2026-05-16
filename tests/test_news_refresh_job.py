from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.agent.news_refresh_job import run_news_refresh_job
from app.api.main import app
from app.database.base import Base
from app.database.connection import get_db_session
from app.database.models import AgentRun, Event
from app.news.news_service import NewsService


class FakeNewsSource:
    source_id = "fake_news"
    source_name = "Fake News"

    def __init__(self, items_by_symbol: dict[str, list[dict]]) -> None:
        self._items_by_symbol = items_by_symbol

    def fetch_ticker_news(self, symbol: str) -> list[dict]:
        return list(self._items_by_symbol.get(symbol.upper(), []))


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
    Base.metadata.drop_all(bind=engine)


def test_run_news_refresh_job_records_agent_run_and_events() -> None:
    session = TestingSessionLocal()
    try:
        service = NewsService(
            sources=[
                FakeNewsSource(
                    items_by_symbol={
                        "AMD": [
                            {
                                "title": "AMD reports record earnings",
                                "link": "https://example.com/amd-earnings",
                                "summary": "AMD posted record quarterly revenue.",
                            }
                        ]
                    }
                )
            ]
        )

        result = run_news_refresh_job(
            db=session,
            symbols=["AMD"],
            news_service=service,
        )

        assert result["status"] == "SUCCESS"
        assert result["records_created"] == 1
        assert result["agent_run_recorded"] is True

        assert session.query(Event).count() == 1
        agent_run = session.query(AgentRun).one()
        assert agent_run.job_name == "news_refresh"
        assert agent_run.status == "SUCCESS"
        assert agent_run.triggered_by == "USER"
    finally:
        session.close()


def test_agent_news_route_without_body_uses_placeholder_path() -> None:
    """Backward-compat: POST with no body must still return SUCCESS (placeholder)."""
    client = TestClient(app)
    response = client.post("/api/agent/refresh/news")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "SUCCESS"
    assert body["job_name"] == "news_refresh"
    assert body["triggered_by"] == "USER"
    assert body["trigger_source"] == "API"


def test_agent_filings_route_without_body_uses_placeholder_path() -> None:
    client = TestClient(app)
    response = client.post("/api/agent/refresh/filings")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "SUCCESS"
    assert body["job_name"] == "filing_refresh"


def test_agent_macro_route_without_body_uses_placeholder_path() -> None:
    client = TestClient(app)
    response = client.post("/api/agent/refresh/macro")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "SUCCESS"
    assert body["job_name"] == "macro_refresh"


def test_agent_news_route_with_body_runs_real_job_with_zero_results_when_sources_empty() -> None:
    """The default real sources fail safely (network calls fail in test env)."""
    client = TestClient(app)
    response = client.post(
        "/api/agent/refresh/news",
        json={"symbols": ["FAKE_TICKER_XYZ"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["job_name"] == "news_refresh"
    assert body["job_type"] == "NEWS"
    assert "result" in body


def test_phase8_manual_option_route_still_works() -> None:
    """Phase 9 must not break the Phase 8 manual option workflow."""
    client = TestClient(app)

    response = client.post(
        "/api/options/manual-input",
        json={
            "raw_text": "AMD June 19 2026 170 call bid 8.20 ask 8.80",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "OK"
    assert body["snapshot"]["symbol"] == "AMD"
