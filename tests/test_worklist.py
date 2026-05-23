"""Phase 27, step 27.12 — tests for Today's Research Worklist.

Covers:

* generator pulls ready / watch / wait from action suggestions;
* PASTE_OPTION_DATA generated only when stock thesis valid + option missing;
* PASTE_OPTION_DATA NOT generated for stock-blocked candidates;
* PASTE_OPTION_DATA NOT generated for STOCK_OK_OPTION_BAD (option complete
  but failed suitability);
* due reviews, risk alerts, important events, experience warnings;
* ranker ordering;
* idempotent regeneration (no duplicate rows per symbol/source/type/day);
* service status transitions;
* route shapes.
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import date, datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.action.action_models import ActionSuggestion
from app.api.main import app
from app.database.base import Base
from app.database.connection import get_db_session
from app.database.models import Event
from app.decision.decision_models import DecisionSnapshot
from app.review.review_models import ReviewQueueItem
from app.risk_control.do_not_touch_models import DoNotTouchItem
from app.worklist.today_worklist_service import TodayWorklistService
from app.worklist.worklist_generator import WorklistGenerator
from app.worklist.worklist_models import ResearchWorklistItem
from app.worklist.worklist_ranker import rank_items
from app.worklist.worklist_types import (
    WORKLIST_ACTION_READY,
    WORKLIST_DUE_REVIEW,
    WORKLIST_EXPERIENCE_WARNING,
    WORKLIST_IMPORTANT_EVENT,
    WORKLIST_PASTE_OPTION_DATA,
    WORKLIST_RISK_ALERT,
)

_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_TestSession = sessionmaker(bind=_engine, autoflush=False, autocommit=False)
TODAY = date(2026, 5, 20)


def _override_get_db_session() -> Generator[Session, None, None]:
    session = _TestSession()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(autouse=True)
def reset_db():
    app.dependency_overrides.clear()
    app.dependency_overrides[get_db_session] = _override_get_db_session
    Base.metadata.drop_all(bind=_engine)
    with _engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS manual_option_snapshots"))
    Base.metadata.create_all(bind=_engine)
    yield
    app.dependency_overrides.clear()


def _seed_action(symbol: str, label: str, **overrides) -> None:
    session = _TestSession()
    defaults = dict(
        symbol=symbol,
        snapshot_date=TODAY,
        final_action_label=label,
        instrument_scope="STOCK_ONLY",
        lifecycle_state="READY_FOR_RESEARCH",
        option_expression_status="OPTION_EXPR_NOT_EVALUATED",
        manual_option_input_needed=False,
        suggested_action_summary=f"{symbol} {label} summary.",
        priority_score=80.0,
        confidence_score=70.0,
    )
    defaults.update(overrides)
    try:
        session.add(ActionSuggestion(**defaults))
        session.commit()
    finally:
        session.close()


def _seed_review(symbol: str, **overrides) -> None:
    session = _TestSession()
    defaults = dict(
        symbol=symbol,
        trigger_type="PRICE_ENTERED_ZONE",
        status="PENDING",
        priority="HIGH",
        summary=f"{symbol} entered entry zone.",
        review_reason_label="PRICE_INSIDE_ENTRY_ZONE",
    )
    defaults.update(overrides)
    try:
        session.add(ReviewQueueItem(**defaults))
        session.commit()
    finally:
        session.close()


def _seed_dnt(symbol: str, **overrides) -> None:
    session = _TestSession()
    defaults = dict(
        symbol=symbol,
        freeze_category="EXTREME_OPTION_VOLATILITY",
        freeze_severity="HARD_FREEZE",
        frozen_at=datetime(2026, 5, 19, tzinfo=timezone.utc),
        release_kind="TIME_BASED",
        release_condition_label="TIME_RELEASE",
        release_condition_description="Releases after the freeze window.",
        reason_summary=f"{symbol} frozen for extreme IV.",
        source_phase="CLASSIFIER",
        triggered_by="AUTOMATIC",
        is_active=True,
    )
    defaults.update(overrides)
    try:
        session.add(DoNotTouchItem(**defaults))
        session.commit()
    finally:
        session.close()


def _seed_event(symbol: str, **overrides) -> None:
    session = _TestSession()
    defaults = dict(
        symbol=symbol,
        event_time=datetime(2026, 5, 20, 9, 0, tzinfo=timezone.utc),
        event_type="NEWS",
        importance_level="HIGH",
        headline=f"{symbol} major headline",
        source="test",
    )
    defaults.update(overrides)
    try:
        session.add(Event(**defaults))
        session.commit()
    finally:
        session.close()


def _seed_decision(symbol: str, memory_risk: str, **overrides) -> None:
    session = _TestSession()
    defaults = dict(
        symbol=symbol,
        snapshot_date=TODAY,
        final_label="WATCH_STOCK_ONLY",
        stock_thesis_label="THESIS_WATCH",
        option_expression_label="OPTION_EXPR_NOT_EVALUATED",
        instrument_scope="STOCK_ONLY",
        event_risk_level="LOW",
        memory_risk_level=memory_risk,
    )
    defaults.update(overrides)
    try:
        session.add(DecisionSnapshot(**defaults))
        session.commit()
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Generator tests
# ---------------------------------------------------------------------------


def test_generator_ready_action_item() -> None:
    _seed_action("AMD", "READY_TO_RESEARCH_STOCK_ONLY")
    session = _TestSession()
    try:
        drafts = WorklistGenerator().generate(session, worklist_date=TODAY)
    finally:
        session.close()
    ready = [d for d in drafts if d.worklist_type == WORKLIST_ACTION_READY]
    assert len(ready) == 1
    assert ready[0].symbol == "AMD"
    assert ready[0].priority == "HIGH"


def test_paste_option_generated_when_stock_valid_option_missing() -> None:
    _seed_action(
        "NVDA",
        "OPTION_DATA_NOT_AVAILABLE",
        option_expression_status="OPTION_EXPR_NOT_EVALUATED",
        manual_option_input_needed=True,
    )
    session = _TestSession()
    try:
        drafts = WorklistGenerator().generate(session, worklist_date=TODAY)
    finally:
        session.close()
    paste = [d for d in drafts if d.worklist_type == WORKLIST_PASTE_OPTION_DATA]
    assert len(paste) == 1
    assert paste[0].symbol == "NVDA"
    assert paste[0].priority == "HIGH"


def test_paste_option_not_generated_when_stock_blocked() -> None:
    # Stock-blocked candidate even if it somehow flagged manual option input.
    _seed_action(
        "ZZZ",
        "INSUFFICIENT_PRICE_HISTORY",
        manual_option_input_needed=True,
        option_expression_status="OPTION_EXPR_NOT_EVALUATED",
    )
    _seed_action(
        "QQQ",
        "NO_TRADE",
        manual_option_input_needed=True,
        option_expression_status="OPTION_EXPR_NOT_EVALUATED",
    )
    session = _TestSession()
    try:
        drafts = WorklistGenerator().generate(session, worklist_date=TODAY)
    finally:
        session.close()
    assert not [d for d in drafts if d.worklist_type == WORKLIST_PASTE_OPTION_DATA]
    # And no primary action item either, since both are blocked.
    assert not [d for d in drafts if d.symbol in ("ZZZ", "QQQ")]


def test_paste_option_not_generated_for_stock_ok_option_bad() -> None:
    # Option data was available + complete and failed suitability — analysis
    # proceeded, so no paste prompt.
    _seed_action(
        "TSLA",
        "STOCK_OK_OPTION_BAD",
        instrument_scope="OPTION_REJECTED",
        option_expression_status="OPTION_EXPR_BAD",
        manual_option_input_needed=True,
    )
    session = _TestSession()
    try:
        drafts = WorklistGenerator().generate(session, worklist_date=TODAY)
    finally:
        session.close()
    assert not [d for d in drafts if d.worklist_type == WORKLIST_PASTE_OPTION_DATA]
    # But it still produces a primary (watch) action item.
    assert [d for d in drafts if d.symbol == "TSLA"]


def test_generator_pulls_all_sources() -> None:
    _seed_action("AMD", "READY_TO_RESEARCH_STOCK_ONLY")
    _seed_review("INTC")
    _seed_dnt("BADCO")
    _seed_event("MSFT")
    _seed_decision("RISKY", "HIGH")
    session = _TestSession()
    try:
        drafts = WorklistGenerator().generate(session, worklist_date=TODAY)
    finally:
        session.close()
    types = {d.worklist_type for d in drafts}
    assert WORKLIST_ACTION_READY in types
    assert WORKLIST_DUE_REVIEW in types
    assert WORKLIST_RISK_ALERT in types
    assert WORKLIST_IMPORTANT_EVENT in types
    assert WORKLIST_EXPERIENCE_WARNING in types


def test_stale_event_filtered_out() -> None:
    _seed_event(
        "OLD",
        event_time=datetime(2026, 5, 1, tzinfo=timezone.utc),
    )
    session = _TestSession()
    try:
        drafts = WorklistGenerator(important_event_window_hours=72).generate(
            session,
            worklist_date=TODAY,
            now=datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc),
        )
    finally:
        session.close()
    assert not [d for d in drafts if d.worklist_type == WORKLIST_IMPORTANT_EVENT]


# ---------------------------------------------------------------------------
# Ranker tests
# ---------------------------------------------------------------------------


def test_ranker_orders_by_priority_then_type() -> None:
    _seed_decision("LOWP", "HIGH")  # LOW priority experience warning
    _seed_dnt("HIGHRISK")  # HIGH priority risk alert
    _seed_action("MIDW", "WAIT_FOR_ENTRY_STOCK_ONLY")  # MEDIUM wait
    session = _TestSession()
    try:
        drafts = WorklistGenerator().generate(session, worklist_date=TODAY)
    finally:
        session.close()
    ranked = rank_items(drafts)
    # Risk alert (HIGH) ranks first, experience warning (LOW) ranks last.
    assert ranked[0].worklist_type == WORKLIST_RISK_ALERT
    assert ranked[-1].worklist_type == WORKLIST_EXPERIENCE_WARNING
    assert all(ranked[i].rank == i + 1 for i in range(len(ranked)))


# ---------------------------------------------------------------------------
# Service tests
# ---------------------------------------------------------------------------


def test_service_persists_and_is_idempotent() -> None:
    _seed_action("AMD", "READY_TO_RESEARCH_STOCK_ONLY")
    _seed_action(
        "NVDA",
        "OPTION_DATA_NOT_AVAILABLE",
        manual_option_input_needed=True,
    )
    svc = TodayWorklistService()
    session = _TestSession()
    try:
        first = svc.generate_worklist(session, worklist_date=TODAY)
        assert first.items_created >= 2
        # Re-run for the same day: no new rows, only refreshes.
        second = svc.generate_worklist(session, worklist_date=TODAY)
        assert second.items_created == 0
        total = (
            session.query(ResearchWorklistItem)
            .filter(ResearchWorklistItem.worklist_date == TODAY)
            .count()
        )
        assert total == first.items_created
    finally:
        session.close()


def test_service_status_transition_preserved_on_regenerate() -> None:
    _seed_action("AMD", "READY_TO_RESEARCH_STOCK_ONLY")
    svc = TodayWorklistService()
    session = _TestSession()
    try:
        svc.generate_worklist(session, worklist_date=TODAY)
        item = (
            session.query(ResearchWorklistItem)
            .filter(ResearchWorklistItem.symbol == "AMD")
            .first()
        )
        svc.transition_status(session, item.id, new_status="DONE")
        # Regenerate: the user-resolved DONE item must not be resurrected/refreshed.
        svc.generate_worklist(session, worklist_date=TODAY)
        session.expire_all()
        again = (
            session.query(ResearchWorklistItem)
            .filter(ResearchWorklistItem.symbol == "AMD")
            .first()
        )
        assert again.status == "DONE"
    finally:
        session.close()


def test_stale_open_item_removed_on_regenerate() -> None:
    _seed_action("AMD", "READY_TO_RESEARCH_STOCK_ONLY")
    svc = TodayWorklistService()
    session = _TestSession()
    try:
        svc.generate_worklist(session, worklist_date=TODAY)
        # Remove the action suggestion -> the OPEN item should be removed.
        session.query(ActionSuggestion).delete()
        session.commit()
        result = svc.generate_worklist(session, worklist_date=TODAY)
        assert result.items_removed >= 1
        remaining = (
            session.query(ResearchWorklistItem)
            .filter(ResearchWorklistItem.symbol == "AMD")
            .count()
        )
        assert remaining == 0
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Route tests
# ---------------------------------------------------------------------------


def test_routes_generate_list_and_transition() -> None:
    _seed_action("AMD", "READY_TO_RESEARCH_STOCK_ONLY")
    client = TestClient(app)

    gen = client.post("/api/worklist/generate", json={"worklist_date": TODAY.isoformat()})
    assert gen.status_code == 200
    assert gen.json()["status"] == "OK"

    listing = client.get("/api/worklist", params={"worklist_date": TODAY.isoformat()})
    assert listing.status_code == 200
    body = listing.json()
    assert body["count"] >= 1
    item = body["items"][0]
    for key in ("id", "symbol", "worklist_type", "source", "priority", "rank", "status"):
        assert key in item

    done = client.post(f"/api/worklist/items/{item['id']}/done", json={})
    assert done.status_code == 200
    assert done.json()["item"]["status"] == "DONE"


def test_route_rejects_bad_status_filter() -> None:
    client = TestClient(app)
    response = client.get("/api/worklist", params={"status": "BOGUS"})
    assert response.status_code == 400
