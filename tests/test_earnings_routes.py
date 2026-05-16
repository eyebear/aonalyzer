from collections.abc import Generator
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.main import app
from app.database.base import Base
from app.database.connection import get_db_session
from app.earnings.earnings_models import EarningsEvent, EarningsRiskSnapshot


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
        now = datetime(2026, 5, 14, 12, 0, tzinfo=timezone.utc)
        today = now.date()

        session.add(
            EarningsEvent(
                symbol="AMD",
                earnings_datetime_utc=now + timedelta(days=5),
                time_of_day="AMC",
                confirmed=False,
                source="test",
                source_url="https://example.com/amd-earnings",
            )
        )
        session.add(
            EarningsEvent(
                symbol="NVDA",
                earnings_datetime_utc=now + timedelta(days=30),
                time_of_day="BMO",
                confirmed=True,
                source="test",
            )
        )
        session.add(
            EarningsRiskSnapshot(
                symbol="AMD",
                snapshot_date=today,
                next_earnings_datetime_utc=now + timedelta(days=5),
                days_to_earnings=5,
                earnings_within_window=True,
                earnings_risk_window_days=7,
                earnings_before_expiration="NOT_APPLICABLE",
                manual_option_expiration_date=None,
                risk_label="EARNINGS_INSIDE_WINDOW",
                risk_reason="Earnings in 5 days.",
                data_sufficiency_status="SUFFICIENT",
            )
        )
        session.add(
            EarningsRiskSnapshot(
                symbol="STOCKONLY",
                snapshot_date=today,
                next_earnings_datetime_utc=None,
                days_to_earnings=None,
                earnings_within_window=False,
                earnings_risk_window_days=7,
                earnings_before_expiration="NOT_APPLICABLE",
                manual_option_expiration_date=None,
                risk_label="EARNINGS_DATA_NOT_AVAILABLE",
                risk_reason="No earnings on file.",
                data_sufficiency_status="EARNINGS_DATA_NOT_AVAILABLE",
            )
        )
        session.commit()
    finally:
        session.close()

    yield

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


client = TestClient(app)


def test_list_earnings_events_returns_all() -> None:
    response = client.get("/api/earnings/events")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 2


def test_list_earnings_events_filter_by_symbol() -> None:
    response = client.get("/api/earnings/events?symbol=AMD")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["events"][0]["source_url"] == "https://example.com/amd-earnings"


def test_list_earnings_risk_snapshots() -> None:
    response = client.get("/api/earnings/risk-snapshots")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 2
    labels = {s["risk_label"] for s in body["snapshots"]}
    assert labels == {"EARNINGS_INSIDE_WINDOW", "EARNINGS_DATA_NOT_AVAILABLE"}


def test_latest_earnings_risk_for_known_symbol() -> None:
    response = client.get("/api/earnings/risk-snapshots/latest?symbol=AMD")
    assert response.status_code == 200
    body = response.json()
    assert body["snapshot"] is not None
    assert body["snapshot"]["risk_label"] == "EARNINGS_INSIDE_WINDOW"
    assert body["snapshot"]["earnings_before_expiration"] == "NOT_APPLICABLE"


def test_latest_earnings_risk_for_unknown_returns_clean_unavailable() -> None:
    response = client.get("/api/earnings/risk-snapshots/latest?symbol=ZZZZ")
    assert response.status_code == 200
    body = response.json()
    assert body["snapshot"] is None
    assert body["data_sufficiency_status"] == "EARNINGS_DATA_NOT_AVAILABLE"


def test_stockonly_symbol_returns_data_not_available_label() -> None:
    """No option data, no earnings rows — still works."""
    response = client.get("/api/earnings/risk-snapshots/latest?symbol=STOCKONLY")
    assert response.status_code == 200
    body = response.json()
    assert body["snapshot"]["risk_label"] == "EARNINGS_DATA_NOT_AVAILABLE"
    assert body["snapshot"]["earnings_before_expiration"] == "NOT_APPLICABLE"


def test_ticker_earnings_risk_endpoint() -> None:
    response = client.get("/api/tickers/AMD/earnings-risk")
    assert response.status_code == 200
    body = response.json()
    assert body["symbol"] == "AMD"
    assert body["snapshot"]["risk_label"] == "EARNINGS_INSIDE_WINDOW"
