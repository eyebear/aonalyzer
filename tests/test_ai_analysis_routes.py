from collections.abc import Generator
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.main import app
from app.database.base import Base
from app.database.connection import get_db_session
from app.database.models import Event
from app.options.manual_option_input_service import ManualOptionInputService

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


def _seed_event() -> int:
    session = TestingSessionLocal()
    try:
        event = Event(
            source="news",
            event_type="NEWS",
            importance_level="HIGH",
            headline="Company beats earnings",
            symbol="AAPL",
            detected_time=datetime.now(timezone.utc),
        )
        session.add(event)
        session.commit()
        session.refresh(event)
        return event.id
    finally:
        session.close()


def test_analyze_event_fallback() -> None:
    event_id = _seed_event()
    client = TestClient(app)
    response = client.post(f"/api/ai-analysis/events/{event_id}")
    assert response.status_code == 200
    analysis = response.json()["analysis"]
    assert analysis["is_fallback"] is True
    assert "Company beats earnings" in analysis["summary"]


def test_get_event_analysis_after_analyze() -> None:
    event_id = _seed_event()
    client = TestClient(app)
    client.post(f"/api/ai-analysis/events/{event_id}")
    response = client.get(f"/api/ai-analysis/events/{event_id}")
    assert response.status_code == 200
    assert response.json()["analysis"]["event_id"] == event_id


def test_analyze_missing_event_404() -> None:
    client = TestClient(app)
    response = client.post("/api/ai-analysis/events/99999")
    assert response.status_code == 404


def test_analyze_option_text_end_to_end() -> None:
    session = TestingSessionLocal()
    try:
        record = ManualOptionInputService().create_manual_snapshot(
            db=session,
            raw_text="AAPL 200 CALL exp 2026-07-15 bid 4.90 ask 5.10",
            symbol="AAPL",
        )
        snapshot_id = record.id
    finally:
        session.close()

    client = TestClient(app)
    response = client.post(f"/api/ai-analysis/options/{snapshot_id}")
    assert response.status_code == 200
    analysis = response.json()["analysis"]
    assert "plain_english_summary" in analysis
    assert "option_interpretation_label" in analysis

    stored = client.get(f"/api/ai-analysis/options/{snapshot_id}")
    assert stored.status_code == 200
    assert stored.json()["ai_status"] in {"AI_OK", "FALLBACK"}
