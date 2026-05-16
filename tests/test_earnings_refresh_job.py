from collections.abc import Generator
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.agent.earnings_calendar_refresh_job import (
    run_earnings_calendar_refresh_job,
)
from app.api.main import app
from app.database.base import Base
from app.database.connection import get_db_session
from app.database.models import AgentRun
from app.earnings.earnings_calendar_service import EarningsCalendarService
from app.earnings.earnings_models import EarningsEvent, EarningsRiskSnapshot


class FakeCalendarSource:
    source_id = "fake_calendar"
    source_name = "Fake Calendar"

    def __init__(self, items_by_symbol: dict[str, list[dict]]) -> None:
        self._items_by_symbol = items_by_symbol

    def fetch_ticker_earnings(self, symbol: str) -> list[dict]:
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


def test_run_job_records_agent_run_and_inserts_event() -> None:
    session = TestingSessionLocal()
    try:
        earnings_dt = datetime.now(timezone.utc) + timedelta(days=5)
        calendar_service = EarningsCalendarService(
            sources=[
                FakeCalendarSource(
                    items_by_symbol={
                        "AMD": [
                            {
                                "earnings_datetime_utc": earnings_dt,
                                "time_of_day": "AMC",
                                "confirmed": False,
                            }
                        ]
                    }
                )
            ]
        )

        result = run_earnings_calendar_refresh_job(
            db=session,
            symbols=["AMD"],
            earnings_calendar_service=calendar_service,
        )

        assert result["status"] == "SUCCESS"
        assert result["records_created"] == 1
        assert result["agent_run_recorded"] is True

        assert session.query(EarningsEvent).count() == 1
        # Risk snapshot is computed automatically (skip_risk_snapshot=False default).
        assert session.query(EarningsRiskSnapshot).count() == 1

        agent_run = session.query(AgentRun).one()
        assert agent_run.job_name == "earnings_refresh"
        assert agent_run.status == "SUCCESS"
    finally:
        session.close()


def test_no_body_post_returns_placeholder_success() -> None:
    client = TestClient(app)
    response = client.post("/api/agent/refresh/earnings")

    assert response.status_code == 200
    body = response.json()
    assert body["job_name"] == "earnings_refresh"
    assert body["status"] == "SUCCESS"
    assert body["triggered_by"] == "USER"
    assert body["trigger_source"] == "API"


def test_body_post_runs_real_job_with_default_safe_empty_source() -> None:
    """Default YahooEarningsCalendarSource returns [] — that's still SUCCESS."""
    client = TestClient(app)
    response = client.post(
        "/api/agent/refresh/earnings",
        json={"symbols": ["AMD"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["job_name"] == "earnings_refresh"
    # Even with empty source we still write a risk snapshot reflecting "no data".
    assert "result" in body


def test_run_job_writes_data_not_available_snapshot_for_stock_only_symbol() -> None:
    session = TestingSessionLocal()
    try:
        # No earnings rows added; the risk snapshot should still be created.
        calendar_service = EarningsCalendarService(
            sources=[FakeCalendarSource(items_by_symbol={})]
        )

        result = run_earnings_calendar_refresh_job(
            db=session,
            symbols=["AMD"],
            earnings_calendar_service=calendar_service,
        )

        assert result["status"] == "SUCCESS"
        assert session.query(EarningsEvent).count() == 0
        risk_rows = session.query(EarningsRiskSnapshot).all()
        assert len(risk_rows) == 1
        assert risk_rows[0].risk_label == "EARNINGS_DATA_NOT_AVAILABLE"
    finally:
        session.close()
