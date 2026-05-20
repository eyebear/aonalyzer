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
from app.options.manual_option_input_service import ManualOptionInputService
from app.options.option_candidate_models import OptionCandidate

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

VALID_LABELS = {
    "OPTION_SUITABLE",
    "OPTION_DATA_NOT_AVAILABLE",
    "OPTION_ANALYSIS_SKIPPED",
    "MANUAL_OPTION_INPUT_NEEDED",
    "STOCK_OK_BUT_OPTION_BAD",
}


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


def _seed_candidate(symbol="AMD") -> None:
    session = TestingSessionLocal()
    try:
        session.add(
            OptionCandidate(
                symbol=symbol,
                snapshot_date=date(2026, 5, 15),
                manual_option_snapshot_id=42,
                option_type="CALL",
                strike=100.0,
                suitability_label="OPTION_SUITABLE",
                is_suitable=True,
                data_sufficiency_status="SUFFICIENT",
                rejection_labels_json=[],
                warning_labels_json=[],
                reasons_json=["ok"],
            )
        )
        session.commit()
    finally:
        session.close()


def test_status_no_option_returns_not_available() -> None:
    client = TestClient(app)
    response = client.get("/api/option-suitability/status", params={"symbol": "AMD"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "OK"
    assert body["result"]["suitability_label"] == "OPTION_DATA_NOT_AVAILABLE"
    assert body["result"]["is_suitable"] is False


def test_latest_returns_clean_state_when_empty() -> None:
    client = TestClient(app)
    response = client.get("/api/option-suitability/candidates/latest", params={"symbol": "AMD"})
    body = response.json()
    assert body["candidate"] is None
    assert body["suitability_label"] == "OPTION_DATA_NOT_AVAILABLE"


def test_list_and_latest_return_seeded_candidate() -> None:
    _seed_candidate()
    client = TestClient(app)

    list_response = client.get("/api/option-suitability/candidates", params={"symbol": "AMD"})
    list_body = list_response.json()
    assert list_body["count"] == 1
    assert list_body["candidates"][0]["suitability_label"] == "OPTION_SUITABLE"

    latest_response = client.get(
        "/api/option-suitability/candidates/latest", params={"symbol": "AMD"}
    )
    assert latest_response.json()["candidate"]["is_suitable"] is True


def test_evaluate_missing_snapshot_returns_404() -> None:
    client = TestClient(app)
    response = client.post("/api/option-suitability/snapshots/999/evaluate")
    assert response.status_code == 404


def test_evaluate_manual_snapshot_end_to_end() -> None:
    # Create a manual snapshot via the Phase 8 service, then evaluate it.
    session = TestingSessionLocal()
    try:
        record = ManualOptionInputService().create_manual_snapshot(
            db=session,
            raw_text="AMD 100 CALL exp 2026-07-15 bid 4.90 ask 5.10 IV 50% OI 2000 vol 500",
            symbol="AMD",
            source_name="test",
        )
        snapshot_id = record.id
    finally:
        session.close()

    client = TestClient(app)
    response = client.post(f"/api/option-suitability/snapshots/{snapshot_id}/evaluate")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "OK"
    candidate = body["candidate"]
    assert candidate["manual_option_snapshot_id"] == snapshot_id
    assert candidate["suitability_label"] in VALID_LABELS
