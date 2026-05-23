"""Phases 34-36 — tests for the pure view helpers + event reviewed-flag route.

Protects the display contracts: manual option review honesty (missing fields,
target-vs-breakeven only when calculable), earnings/IV risk honesty (no fake IV
risk, earnings-before-expiration only when an expiration exists, IV crush only
when calculable), and deterministic event filtering + reviewed-flag persistence.
"""

from __future__ import annotations

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
from app.ui_experience.event_views import build_event_row, filter_events
from app.ui_experience.option_views import (
    build_manual_option_review_row,
    target_vs_breakeven,
)
from app.ui_experience.risk_views import (
    IV_STATE_UNAVAILABLE,
    build_earnings_iv_view,
)

# --- Phase 34: option_views ------------------------------------------------


def test_manual_option_row_shows_missing_fields() -> None:
    snapshot = {
        "id": 1,
        "symbol": "AMD",
        "option_type": "CALL",
        "strike": 170.0,
        "last_price": None,
        "mid_price": 8.5,
        "implied_volatility": None,
        "delta": None,
        "missing_fields": ["implied_volatility", "delta"],
        "data_quality_status": "INSUFFICIENT_OPTION_DATA",
        "parser_confidence": "MEDIUM",
    }
    row = build_manual_option_review_row(snapshot)
    assert row["premium"] == 8.5  # falls back to mid price
    assert row["implied_volatility"] is None  # not invented
    assert row["missing_fields"] == ["implied_volatility", "delta"]


def test_target_vs_breakeven_only_when_calculable() -> None:
    assert target_vs_breakeven(target_price=None, breakeven=178.5)["calculable"] is False
    result = target_vs_breakeven(target_price=185.0, breakeven=178.5)
    assert result["calculable"] is True
    assert result["target_above_breakeven"] is True
    assert result["margin"] == pytest.approx(6.5)


# --- Phase 35: risk_views --------------------------------------------------


def test_iv_unavailable_when_no_iv_data() -> None:
    view = build_earnings_iv_view(earnings={"days_to_earnings": 3}, iv=None)
    assert view["iv"]["state"] == IV_STATE_UNAVAILABLE
    assert view["iv"]["available"] is False
    # IV crush is not fabricated when IV is missing.
    assert view["iv_crush_risk"]["calculable"] is False


def test_earnings_before_expiration_only_when_expiration_exists() -> None:
    earnings = {
        "days_to_earnings": 3,
        "earnings_before_expiration": "TRUE",
    }
    without = build_earnings_iv_view(earnings=earnings, iv=None, option_expiration_present=False)
    assert (
        without["earnings"]["earnings_before_expiration"] == "NOT_APPLICABLE_NO_OPTION_EXPIRATION"
    )
    with_exp = build_earnings_iv_view(earnings=earnings, iv=None, option_expiration_present=True)
    assert with_exp["earnings"]["earnings_before_expiration"] == "TRUE"


def test_iv_crush_calculable_with_iv_and_earnings() -> None:
    view = build_earnings_iv_view(
        earnings={"days_to_earnings": 2, "earnings_within_window": True},
        iv={"current_iv": 0.7, "iv_rank": 80.0},
    )
    crush = view["iv_crush_risk"]
    assert crush["calculable"] is True
    assert crush["level"] == "HIGH"


# --- Phase 36: event_views -------------------------------------------------


def test_filter_events_by_window_and_importance() -> None:
    now = datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)
    events = [
        {
            "symbol": "AMD",
            "importance_level": "HIGH",
            "event_type": "NEWS",
            "event_time": "2026-05-20T09:00:00+00:00",
        },
        {
            "symbol": "AMD",
            "importance_level": "LOW",
            "event_type": "NEWS",
            "event_time": "2026-05-01T09:00:00+00:00",
        },
    ]
    fresh_high = filter_events(events, date_window="24h", importance_level="HIGH", now=now)
    assert len(fresh_high) == 1
    all_news = filter_events(events, date_window="all", event_type="NEWS", now=now)
    assert len(all_news) == 2


def test_event_row_source_link_only_when_available() -> None:
    with_link = build_event_row({"id": 1, "source_url": "https://x.test/a"})
    assert with_link["has_source_link"] is True
    without = build_event_row({"id": 2, "source_url": None})
    assert without["has_source_link"] is False


# --- Phase 36.10: reviewed-flag persistence (route) ------------------------

_engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
)
_TestSession = sessionmaker(bind=_engine, autoflush=False, autocommit=False)


def _override_get_db_session() -> Generator[Session, None, None]:
    session = _TestSession()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client():
    app.dependency_overrides.clear()
    app.dependency_overrides[get_db_session] = _override_get_db_session
    Base.metadata.drop_all(bind=_engine)
    Base.metadata.create_all(bind=_engine)
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_event_reviewed_flag_persists(client) -> None:
    session = _TestSession()
    try:
        event = Event(
            symbol="AMD",
            event_time=datetime(2026, 5, 20, tzinfo=timezone.utc),
            event_type="NEWS",
            importance_level="HIGH",
            headline="Test",
            source="test",
            is_reviewed=False,
        )
        session.add(event)
        session.commit()
        event_id = event.id
    finally:
        session.close()

    resp = client.post(f"/api/events/{event_id}/reviewed", json={"reviewed": True})
    assert resp.status_code == 200
    assert resp.json()["event"]["is_reviewed"] is True

    fetched = client.get(f"/api/events/{event_id}")
    assert fetched.json()["event"]["is_reviewed"] is True
