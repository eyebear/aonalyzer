from collections.abc import Generator
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.main import app
from app.database.base import Base
from app.database.connection import get_db_session
from app.iv_history.iv_models import IvHistoryDay, IvRiskSnapshot

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
        start = date(2026, 4, 1)
        for i in range(40):
            session.add(
                IvHistoryDay(
                    symbol="AMD",
                    snapshot_date=start + timedelta(days=i),
                    atm_iv_30d=0.20 + (i % 7) * 0.01,
                    source="test",
                )
            )
        session.add(
            IvRiskSnapshot(
                symbol="AMD",
                snapshot_date=date(2026, 5, 14),
                current_iv=0.25,
                iv_rank=45.0,
                iv_percentile=40.0,
                iv_history_days_used=40,
                iv_warning_threshold=70.0,
                iv_reject_threshold=85.0,
                risk_label="IV_LOW",
                risk_reason="IV rank 45.0 below warning threshold 70.0.",
                data_sufficiency_status="SUFFICIENT",
            )
        )
        session.add(
            IvRiskSnapshot(
                symbol="STOCKONLY",
                snapshot_date=date(2026, 5, 14),
                current_iv=None,
                iv_rank=None,
                iv_percentile=None,
                iv_history_days_used=0,
                iv_warning_threshold=70.0,
                iv_reject_threshold=85.0,
                risk_label="IV_DATA_NOT_AVAILABLE",
                risk_reason="No IV history.",
                data_sufficiency_status="IV_DATA_NOT_AVAILABLE",
            )
        )
        session.commit()
    finally:
        session.close()

    yield

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


client = TestClient(app)


def test_iv_history_for_known_symbol() -> None:
    response = client.get("/api/iv/history?symbol=AMD")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 40
    assert body["data_sufficiency_status"] == "SUFFICIENT"


def test_iv_history_for_unknown_returns_unavailable() -> None:
    response = client.get("/api/iv/history?symbol=ZZZZ")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 0
    assert body["data_sufficiency_status"] == "IV_DATA_NOT_AVAILABLE"
    assert body["history"] == []


def test_iv_risk_snapshots_list() -> None:
    response = client.get("/api/iv/risk-snapshots")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 2
    labels = {s["risk_label"] for s in body["snapshots"]}
    assert labels == {"IV_LOW", "IV_DATA_NOT_AVAILABLE"}


def test_latest_iv_risk_for_unknown_symbol() -> None:
    response = client.get("/api/iv/risk-snapshots/latest?symbol=ZZZZ")
    assert response.status_code == 200
    body = response.json()
    assert body["snapshot"] is None
    assert body["data_sufficiency_status"] == "IV_DATA_NOT_AVAILABLE"


def test_latest_iv_risk_for_stock_only_symbol_returns_unavailable_label() -> None:
    response = client.get("/api/iv/risk-snapshots/latest?symbol=STOCKONLY")
    assert response.status_code == 200
    body = response.json()
    assert body["snapshot"]["risk_label"] == "IV_DATA_NOT_AVAILABLE"
    assert body["snapshot"]["iv_rank"] is None
    assert body["snapshot"]["iv_percentile"] is None


def test_ticker_iv_risk_endpoint() -> None:
    response = client.get("/api/tickers/AMD/iv-risk")
    assert response.status_code == 200
    body = response.json()
    assert body["symbol"] == "AMD"
    assert body["snapshot"]["iv_rank"] == 45.0
