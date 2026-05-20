from collections.abc import Generator
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.agent.technical_refresh_job import run_technical_refresh_job
from app.api.main import app
from app.database.base import Base
from app.database.connection import get_db_session
from app.database.models import AgentRun, DailyPrice
from app.quant.technical_analysis_service import TechnicalAnalysisService
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

    yield

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


def _seed_daily_prices(session: Session, symbol: str, closes: list[float]) -> None:
    cursor = date(2026, 1, 1) - timedelta(days=len(closes))
    for index, close in enumerate(closes):
        session.add(
            DailyPrice(
                symbol=symbol,
                price_date=cursor + timedelta(days=index),
                open_price=close,
                high_price=close + 1.0,
                low_price=close - 1.0,
                close_price=close,
                adjusted_close_price=close,
                volume=100_000,
                source="test",
            )
        )
    session.commit()


def test_run_technical_refresh_job_records_agent_run_and_snapshot() -> None:
    session = TestingSessionLocal()
    try:
        _seed_daily_prices(
            session,
            "AMD",
            [100.0 + i * 0.25 for i in range(60)],
        )

        result = run_technical_refresh_job(
            db=session,
            symbols=["AMD"],
            technical_service=TechnicalAnalysisService(),
        )

        assert result["status"] == "SUCCESS"
        assert result["records_created"] == 1
        assert result["agent_run_recorded"] is True

        assert session.query(TechnicalSnapshot).count() == 1
        agent_run = session.query(AgentRun).one()
        assert agent_run.job_name == "technical_refresh"
        assert agent_run.status == "SUCCESS"
    finally:
        session.close()


def test_run_technical_refresh_job_with_insufficient_history_is_clean() -> None:
    session = TestingSessionLocal()
    try:
        _seed_daily_prices(session, "NEW", [10.0, 11.0, 12.0])

        result = run_technical_refresh_job(
            db=session,
            symbols=["NEW"],
            technical_service=TechnicalAnalysisService(),
        )

        # No row inserted, but the job runs successfully (no failure).
        assert result["status"] == "SUCCESS"
        assert result["records_created"] == 0
        assert session.query(TechnicalSnapshot).count() == 0
        assert "NEW" in result["result"]["insufficient_symbols"]
    finally:
        session.close()


def test_run_technical_refresh_job_updates_existing_snapshot_on_rerun() -> None:
    session = TestingSessionLocal()
    try:
        _seed_daily_prices(
            session,
            "AMD",
            [100.0 + i * 0.25 for i in range(60)],
        )
        service = TechnicalAnalysisService()

        first = run_technical_refresh_job(
            db=session, symbols=["AMD"], technical_service=service
        )
        second = run_technical_refresh_job(
            db=session, symbols=["AMD"], technical_service=service
        )

        assert first["records_created"] == 1
        assert second["records_created"] == 0
        assert second["records_updated"] == 1
        assert session.query(TechnicalSnapshot).count() == 1
    finally:
        session.close()


def test_agent_route_no_body_returns_placeholder_success() -> None:
    """Backward-compat: body-less POST falls through to ManualRefreshController."""
    client = TestClient(app)
    response = client.post("/api/agent/refresh/technical")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "SUCCESS"
    assert body["job_name"] == "technical_refresh"
    assert body["triggered_by"] == "USER"
    assert body["trigger_source"] == "API"


def test_agent_route_with_body_runs_real_job_and_persists() -> None:
    session = TestingSessionLocal()
    try:
        _seed_daily_prices(
            session,
            "AMD",
            [100.0 + i * 0.25 for i in range(60)],
        )
    finally:
        session.close()

    client = TestClient(app)
    response = client.post(
        "/api/agent/refresh/technical",
        json={"symbols": ["AMD"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["job_name"] == "technical_refresh"
    assert body["job_type"] == "TECHNICAL"
    assert body["records_created"] == 1

    # Confirm the persisted row is queryable through the API.
    list_response = client.get("/api/technical/snapshots?symbol=AMD")
    assert list_response.status_code == 200
    list_body = list_response.json()
    assert list_body["count"] == 1


def test_phase11_does_not_require_option_data() -> None:
    """No option tables exist in this fixture — the workflow still works."""
    session = TestingSessionLocal()
    try:
        # Sanity: option tables truly absent.
        table_names = {
            row[0]
            for row in session.execute(
                text("SELECT name FROM sqlite_master WHERE type='table'")
            )
        }
        assert "manual_option_snapshots" not in table_names

        _seed_daily_prices(
            session,
            "AMD",
            [100.0 + i * 0.25 for i in range(60)],
        )
    finally:
        session.close()

    client = TestClient(app)
    response = client.post(
        "/api/agent/refresh/technical",
        json={"symbols": ["AMD"]},
    )

    assert response.status_code == 200
    assert response.json()["records_created"] == 1


def test_phase8_manual_option_route_still_works() -> None:
    """Cohabitation check — Phase 8 endpoint must still respond cleanly."""
    client = TestClient(app)
    response = client.post(
        "/api/options/manual-input",
        json={"raw_text": "AMD June 19 2026 170 call bid 8.20 ask 8.80"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "OK"
    assert body["snapshot"]["symbol"] == "AMD"
