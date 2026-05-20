from collections.abc import Generator
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.main import app
from app.database.base import Base
from app.database.connection import get_db_session
from app.database.models import Event

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
        now = datetime.now(timezone.utc)

        session.add_all(
            [
                Event(
                    event_time=now - timedelta(hours=1),
                    detected_time=now - timedelta(hours=1),
                    source="google_news",
                    source_url="https://example.com/amd-earnings",
                    source_title="Google News",
                    symbol="AMD",
                    event_type="NEWS",
                    importance_level="HIGH",
                    headline="AMD reports record earnings",
                    raw_summary="AMD posted record quarterly revenue.",
                    content_hash="hash_amd_earnings",
                    event_metadata_json={"provider": "google_news"},
                    is_reviewed=False,
                ),
                Event(
                    event_time=now - timedelta(hours=12),
                    detected_time=now - timedelta(hours=12),
                    source="sec_edgar",
                    source_url="https://www.sec.gov/Archives/amd-10q",
                    source_title="SEC EDGAR",
                    symbol="AMD",
                    event_type="FILING",
                    importance_level="MEDIUM",
                    headline="AMD 10-Q quarterly filing",
                    raw_summary="",
                    content_hash="hash_amd_10q",
                    event_metadata_json={"filing_type": "10-Q"},
                    is_reviewed=False,
                ),
                Event(
                    event_time=now - timedelta(days=30),
                    detected_time=now - timedelta(days=30),
                    source="econ_calendar",
                    source_url="https://www.federalreserve.gov/fomc",
                    source_title="Federal Reserve",
                    symbol=None,
                    event_type="MACRO",
                    importance_level="HIGH",
                    headline="Old FOMC release",
                    raw_summary="",
                    content_hash="hash_old_fomc",
                    event_metadata_json={},
                    is_reviewed=False,
                ),
                Event(
                    event_time=now - timedelta(hours=2),
                    detected_time=now - timedelta(hours=2),
                    source="google_news",
                    source_url="https://example.com/nvda-1",
                    source_title="Google News",
                    symbol="NVDA",
                    event_type="NEWS",
                    importance_level="LOW",
                    headline="NVDA general market color piece",
                    raw_summary="",
                    content_hash="hash_nvda_color",
                    event_metadata_json={},
                    is_reviewed=False,
                ),
            ]
        )
        session.commit()
    finally:
        session.close()

    yield

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


client = TestClient(app)


def test_list_events_default_returns_all_events_with_source_url_and_importance() -> None:
    response = client.get("/api/events")
    assert response.status_code == 200

    body = response.json()
    assert body["status"] == "OK"
    assert body["count"] == 4

    for event in body["events"]:
        assert "source_url" in event
        assert "importance_level" in event
        assert event["importance_level"] in {"HIGH", "MEDIUM", "LOW"}
        assert "freshness" in event
        assert "is_fresh" in event["freshness"]
        assert "is_stale" in event["freshness"]


def test_list_events_filter_by_symbol() -> None:
    response = client.get("/api/events?symbol=AMD")
    assert response.status_code == 200

    body = response.json()
    assert body["count"] == 2
    assert {e["symbol"] for e in body["events"]} == {"AMD"}


def test_list_events_filter_by_event_type() -> None:
    response = client.get("/api/events?event_type=FILING")
    assert response.status_code == 200

    body = response.json()
    assert body["count"] == 1
    assert body["events"][0]["event_type"] == "FILING"


def test_list_events_filter_by_importance() -> None:
    response = client.get("/api/events?importance_level=HIGH")
    assert response.status_code == 200

    body = response.json()
    assert body["count"] == 2
    assert all(e["importance_level"] == "HIGH" for e in body["events"])


def test_list_events_filter_by_source() -> None:
    response = client.get("/api/events?source=sec_edgar")
    assert response.status_code == 200

    body = response.json()
    assert body["count"] == 1
    assert body["events"][0]["source"] == "sec_edgar"


def test_list_events_invalid_event_type_returns_400() -> None:
    response = client.get("/api/events?event_type=NOT_A_TYPE")
    assert response.status_code == 400


def test_list_events_invalid_importance_returns_400() -> None:
    response = client.get("/api/events?importance_level=URGENT")
    assert response.status_code == 400


def test_recent_events_filters_by_window_hours() -> None:
    response = client.get("/api/events/recent?hours=24")
    assert response.status_code == 200

    body = response.json()
    # 3 events are within 24h (AMD earnings, AMD 10-Q, NVDA), the old FOMC is excluded.
    assert body["window_hours"] == 24
    assert body["count"] == 3
    assert all(
        event["source_url"] for event in body["events"] if event["source_url"]
    )


def test_recent_events_returns_high_medium_low_labels() -> None:
    response = client.get("/api/events/recent?hours=48")
    assert response.status_code == 200

    body = response.json()
    importance_levels = {event["importance_level"] for event in body["events"]}
    # We seeded HIGH, MEDIUM, and LOW within 48h.
    assert importance_levels == {"HIGH", "MEDIUM", "LOW"}


def test_recent_events_excludes_stale_event() -> None:
    response = client.get("/api/events/recent?hours=24")
    body = response.json()
    headlines = {event["headline"] for event in body["events"]}
    assert "Old FOMC release" not in headlines


def test_stale_event_is_identifiable_by_freshness() -> None:
    response = client.get("/api/events?event_type=MACRO")
    body = response.json()

    assert body["count"] == 1
    stale_event = body["events"][0]
    assert stale_event["freshness"]["is_stale"] is True
    assert stale_event["freshness"]["is_fresh"] is False


def test_get_event_by_id_returns_source_url() -> None:
    list_response = client.get("/api/events?event_type=FILING")
    event_id = list_response.json()["events"][0]["id"]

    response = client.get(f"/api/events/{event_id}")
    assert response.status_code == 200

    body = response.json()
    assert body["event"]["event_type"] == "FILING"
    assert body["event"]["source_url"] == "https://www.sec.gov/Archives/amd-10q"


def test_get_event_by_id_returns_404_for_missing() -> None:
    response = client.get("/api/events/9999999")
    assert response.status_code == 404


def test_ticker_events_endpoint_returns_only_that_symbol() -> None:
    response = client.get("/api/tickers/AMD/events")
    assert response.status_code == 200

    body = response.json()
    assert body["symbol"] == "AMD"
    assert body["count"] == 2
    assert {e["symbol"] for e in body["events"]} == {"AMD"}


def test_event_api_works_with_no_option_data() -> None:
    """Sanity: nothing in events depends on manual_option_snapshots or option_chain."""
    response = client.get("/api/events")
    assert response.status_code == 200

    body = response.json()
    assert body["status"] == "OK"
    for event in body["events"]:
        assert "option" not in event
        assert event["event_type"] in {
            "NEWS",
            "FILING",
            "MACRO",
            "COMPANY_IR",
            "OPTION_ANOMALY",
            "TECHNICAL_TRIGGER",
            "RISK_ALERT",
            "SYSTEM_EVENT",
        }
