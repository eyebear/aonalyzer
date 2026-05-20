from collections.abc import Generator
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.agent.stock_setup_refresh_job import run_stock_setup_refresh_job
from app.api.main import app
from app.database.base import Base
from app.database.connection import get_db_session
from app.database.models import AgentRun, DailyPrice
from app.quant.stock_setup_models import StockSetup
from app.quant.stock_setup_service import StockSetupService

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


def _seed_v_pattern_prices(session: Session, symbol: str) -> None:
    # 15-row series with a clear swing low at index 5 and a swing high at
    # index 10, ending at "current close" = 100. Both swings have ≥2 rows
    # of context on each side, so window=2 detection finds them.
    series = [
        (100.0, 101.0, 98.0, 100.0),
        (100.0, 100.0, 97.0, 99.0),
        (99.0, 99.0, 96.0, 98.0),
        (98.0, 98.0, 97.0, 97.5),
        (97.5, 97.0, 96.0, 96.5),
        (96.5, 96.0, 95.0, 95.5),
        (95.5, 97.0, 96.0, 96.5),
        (96.5, 99.0, 96.5, 98.5),
        (98.5, 101.0, 97.0, 100.0),
        (100.0, 104.0, 99.0, 102.0),
        (102.0, 110.0, 100.0, 108.0),
        (108.0, 109.0, 105.0, 106.0),
        (106.0, 107.0, 103.0, 104.0),
        (104.0, 105.0, 101.0, 102.0),
        (102.0, 103.0, 99.0, 100.0),
    ]
    cursor = date(2026, 1, 1) - timedelta(days=len(series))
    for index, (open_p, high_p, low_p, close_p) in enumerate(series):
        session.add(
            DailyPrice(
                symbol=symbol,
                price_date=cursor + timedelta(days=index),
                open_price=open_p,
                high_price=high_p,
                low_price=low_p,
                close_price=close_p,
                adjusted_close_price=close_p,
                volume=100_000,
                source="test",
            )
        )
    session.commit()


def test_run_job_records_agent_run_and_persists_setup() -> None:
    session = TestingSessionLocal()
    try:
        _seed_v_pattern_prices(session, "AMD")

        result = run_stock_setup_refresh_job(
            db=session,
            symbols=["AMD"],
            stock_setup_service=StockSetupService(swing_window=2),
        )

        assert result["status"] == "SUCCESS"
        assert result["records_created"] == 1
        assert result["agent_run_recorded"] is True

        assert session.query(StockSetup).count() == 1
        agent_run = session.query(AgentRun).one()
        assert agent_run.job_name == "stock_setup_refresh"
        assert agent_run.status == "SUCCESS"
    finally:
        session.close()


def test_run_job_with_insufficient_history_is_clean() -> None:
    session = TestingSessionLocal()
    try:
        # Only 2 rows — below MINIMUM_PRICE_ROWS_FOR_SWINGS=5
        for i in range(2):
            session.add(
                DailyPrice(
                    symbol="NEW",
                    price_date=date(2026, 1, 1) + timedelta(days=i),
                    open_price=10.0,
                    high_price=11.0,
                    low_price=9.0,
                    close_price=10.5,
                    adjusted_close_price=10.5,
                    volume=100,
                    source="test",
                )
            )
        session.commit()

        result = run_stock_setup_refresh_job(
            db=session,
            symbols=["NEW"],
            stock_setup_service=StockSetupService(swing_window=2),
        )

        # Job succeeds; the insufficient snapshot is persisted.
        assert result["status"] == "SUCCESS"
        assert session.query(StockSetup).count() == 1
        row = session.query(StockSetup).one()
        assert row.data_sufficiency_status == "INSUFFICIENT_PRICE_HISTORY"
        assert row.direction == "UNDEFINED"
    finally:
        session.close()


def test_run_job_updates_existing_setup_on_rerun() -> None:
    session = TestingSessionLocal()
    try:
        _seed_v_pattern_prices(session, "AMD")
        service = StockSetupService(swing_window=2)

        first = run_stock_setup_refresh_job(
            db=session, symbols=["AMD"], stock_setup_service=service
        )
        second = run_stock_setup_refresh_job(
            db=session, symbols=["AMD"], stock_setup_service=service
        )

        assert first["records_created"] == 1
        assert second["records_created"] == 0
        assert second["records_updated"] == 1
        assert session.query(StockSetup).count() == 1
    finally:
        session.close()


def test_no_body_post_returns_placeholder_success() -> None:
    client = TestClient(app)
    response = client.post("/api/agent/refresh/stock-setup")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "SUCCESS"
    assert body["job_name"] == "stock_setup_refresh"
    assert body["triggered_by"] == "USER"
    assert body["trigger_source"] == "API"


def test_body_post_runs_real_job_and_is_queryable() -> None:
    session = TestingSessionLocal()
    try:
        _seed_v_pattern_prices(session, "AMD")
    finally:
        session.close()

    client = TestClient(app)
    response = client.post(
        "/api/agent/refresh/stock-setup",
        json={"symbols": ["AMD"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["job_name"] == "stock_setup_refresh"
    assert body["records_created"] == 1

    list_response = client.get("/api/setups?symbol=AMD")
    assert list_response.status_code == 200
    list_body = list_response.json()
    assert list_body["count"] == 1


def test_phase12_does_not_require_option_data() -> None:
    session = TestingSessionLocal()
    try:
        # Confirm option tables are not in the DB.
        table_names = {
            row[0]
            for row in session.execute(
                text("SELECT name FROM sqlite_master WHERE type='table'")
            )
        }
        assert "manual_option_snapshots" not in table_names

        _seed_v_pattern_prices(session, "AMD")
    finally:
        session.close()

    client = TestClient(app)
    response = client.post(
        "/api/agent/refresh/stock-setup",
        json={"symbols": ["AMD"]},
    )

    assert response.status_code == 200
    assert response.json()["records_created"] == 1


def test_phase8_manual_option_route_still_works_alongside_setup_job() -> None:
    """Cohabitation — Phase 8 endpoint must still respond cleanly."""
    client = TestClient(app)
    response = client.post(
        "/api/options/manual-input",
        json={"raw_text": "AMD June 19 2026 170 call bid 8.20 ask 8.80"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "OK"
    assert body["snapshot"]["symbol"] == "AMD"
