from collections.abc import Generator
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.agent.iv_risk_refresh_job import run_iv_risk_refresh_job
from app.api.main import app
from app.database.base import Base
from app.database.connection import get_db_session
from app.database.models import AgentRun
from app.iv_history.iv_history_service import IvHistoryService
from app.iv_history.iv_models import IvHistoryDay, IvRiskSnapshot
from app.iv_history.iv_risk_service import IvRiskService


class FakeIvHistorySource:
    source_id = "fake_iv"
    source_name = "Fake IV"

    def __init__(self, items_by_symbol: dict[str, list[dict]]) -> None:
        self._items_by_symbol = items_by_symbol

    def fetch_ticker_iv_history(self, symbol: str) -> list[dict]:
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


def test_run_job_inserts_iv_history_and_computes_snapshot() -> None:
    session = TestingSessionLocal()
    try:
        start = date(2026, 4, 1)
        items = [
            {
                "snapshot_date": start + timedelta(days=i),
                "atm_iv_30d": 0.20 + (i % 7) * 0.01,
            }
            for i in range(40)
        ]
        iv_history_service = IvHistoryService(
            sources=[FakeIvHistorySource(items_by_symbol={"AMD": items})]
        )

        result = run_iv_risk_refresh_job(
            db=session,
            symbols=["AMD"],
            iv_history_service=iv_history_service,
            iv_risk_service=IvRiskService(minimum_history_days=30),
        )

        assert result["status"] == "SUCCESS"
        assert session.query(IvHistoryDay).count() == 40
        assert session.query(IvRiskSnapshot).count() == 1
        agent_run = session.query(AgentRun).one()
        assert agent_run.job_name == "iv_risk_refresh"
        assert agent_run.status == "SUCCESS"
    finally:
        session.close()


def test_no_body_post_returns_placeholder_success() -> None:
    client = TestClient(app)
    response = client.post("/api/agent/refresh/iv-risk")

    assert response.status_code == 200
    body = response.json()
    assert body["job_name"] == "iv_risk_refresh"
    assert body["status"] == "SUCCESS"


def test_body_post_runs_real_job_against_empty_default_source() -> None:
    client = TestClient(app)
    response = client.post(
        "/api/agent/refresh/iv-risk",
        json={"symbols": ["AMD"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["job_name"] == "iv_risk_refresh"
    # Default source returns no history → IV_DATA_NOT_AVAILABLE snapshot written.


def test_run_job_for_stock_only_writes_iv_data_not_available_snapshot() -> None:
    """Phase 10 rule: stock-only research continues normally without IV."""
    session = TestingSessionLocal()
    try:
        iv_history_service = IvHistoryService(
            sources=[FakeIvHistorySource(items_by_symbol={})]
        )

        result = run_iv_risk_refresh_job(
            db=session,
            symbols=["AMD"],
            iv_history_service=iv_history_service,
            iv_risk_service=IvRiskService(minimum_history_days=30),
        )

        assert result["status"] == "SUCCESS"
        assert session.query(IvHistoryDay).count() == 0
        risk_rows = session.query(IvRiskSnapshot).all()
        assert len(risk_rows) == 1
        assert risk_rows[0].risk_label == "IV_DATA_NOT_AVAILABLE"
    finally:
        session.close()


def test_phase8_manual_option_route_still_works_alongside_iv_job() -> None:
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
