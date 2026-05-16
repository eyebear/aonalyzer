from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.base import Base
from app.database.models import Event
from app.event_normalizer.event_labels import ImportanceLevel
from app.event_normalizer.event_normalizer import EventNormalizer
from app.event_normalizer.freshness import EventFreshnessChecker


def create_test_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)

    SessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine,
    )

    return engine, SessionLocal()


def test_normalize_raw_event_preserves_source_url() -> None:
    normalizer = EventNormalizer()

    normalized = normalizer.normalize_raw_event(
        raw_event={
            "title": "AMD reports record earnings",
            "url": "https://example.com/amd-earnings",
            "summary": "AMD posted record quarterly revenue.",
            "symbol": "AMD",
        },
        default_event_type="NEWS",
        default_source="google_news",
    )

    assert normalized is not None
    assert normalized.event_type == "NEWS"
    assert normalized.source == "google_news"
    assert normalized.source_url == "https://example.com/amd-earnings"
    assert normalized.headline == "AMD reports record earnings"
    assert normalized.symbol == "AMD"
    assert normalized.importance_level == ImportanceLevel.HIGH.value


def test_normalize_returns_none_when_required_fields_missing() -> None:
    normalizer = EventNormalizer()

    assert (
        normalizer.normalize_raw_event(
            raw_event={"title": "", "url": "https://example.com/x"},
            default_event_type="NEWS",
            default_source="google_news",
        )
        is None
    )

    assert (
        normalizer.normalize_raw_event(
            raw_event={"title": "Some headline"},
            default_event_type="NEWS",
            default_source="",
        )
        is None
    )


def test_normalize_batch_routes_invalid_to_rejected() -> None:
    normalizer = EventNormalizer()

    result = normalizer.normalize_batch(
        raw_events=[
            {"title": "Good headline", "url": "https://example.com/a", "symbol": "AMD"},
            {"title": "", "url": "https://example.com/b"},
        ],
        default_event_type="NEWS",
        default_source="google_news",
    )

    assert len(result.normalized) == 1
    assert len(result.rejected) == 1
    assert result.rejected[0]["reason"].startswith("missing")


def test_persist_events_inserts_and_dedupes() -> None:
    _, db = create_test_session()
    normalizer = EventNormalizer()

    batch = normalizer.normalize_batch(
        raw_events=[
            {
                "title": "AMD beats earnings",
                "url": "https://example.com/amd-1",
                "symbol": "AMD",
            },
            {
                "title": "AMD beats earnings",
                "url": "https://example.com/amd-1",
                "symbol": "AMD",
            },
        ],
        default_event_type="NEWS",
        default_source="google_news",
    )

    persist_result = normalizer.persist_events(db=db, events=batch.normalized)
    db.commit()

    assert persist_result.inserted_count == 1
    assert persist_result.duplicate_count == 1
    assert db.query(Event).count() == 1


def test_persist_dedupes_against_existing_db_rows() -> None:
    _, db = create_test_session()
    normalizer = EventNormalizer()

    raw = {
        "title": "AMD beats earnings",
        "url": "https://example.com/amd-1",
        "symbol": "AMD",
    }

    first_batch = normalizer.normalize_batch(
        raw_events=[raw],
        default_event_type="NEWS",
        default_source="google_news",
    )
    normalizer.persist_events(db=db, events=first_batch.normalized)
    db.commit()

    second_batch = normalizer.normalize_batch(
        raw_events=[raw],
        default_event_type="NEWS",
        default_source="google_news",
    )
    second_persist = normalizer.persist_events(db=db, events=second_batch.normalized)
    db.commit()

    assert second_persist.inserted_count == 0
    assert second_persist.duplicate_count == 1
    assert db.query(Event).count() == 1


def test_multi_ticker_story_creates_one_row_per_symbol() -> None:
    _, db = create_test_session()
    normalizer = EventNormalizer()

    raw = {
        "title": "Chipmakers rally on AI demand",
        "url": "https://example.com/rally",
    }

    for symbol in ["AMD", "NVDA"]:
        batch = normalizer.normalize_batch(
            raw_events=[raw],
            default_event_type="NEWS",
            default_source="google_news",
            symbol=symbol,
        )
        normalizer.persist_events(db=db, events=batch.normalized)

    db.commit()

    rows = db.query(Event).order_by(Event.symbol).all()
    assert {row.symbol for row in rows} == {"AMD", "NVDA"}
    assert len({row.content_hash for row in rows}) == 2


def test_freshness_checker_identifies_stale_events() -> None:
    checker = EventFreshnessChecker(fresh_window_hours=24, stale_window_days=7)
    now = datetime(2026, 5, 14, 12, 0, tzinfo=timezone.utc)

    fresh = checker.check(event_time=now - timedelta(hours=1), now=now)
    assert fresh.is_fresh is True
    assert fresh.is_stale is False

    stale = checker.check(event_time=now - timedelta(days=30), now=now)
    assert stale.is_fresh is False
    assert stale.is_stale is True

    missing = checker.check(event_time=None, now=now)
    assert missing.is_fresh is False
    assert missing.is_stale is False
    assert missing.age_minutes is None
