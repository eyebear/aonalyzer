from datetime import datetime, timezone

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.data_quality.data_quality_models import DataFreshness
from app.database.base import Base
from app.database.models import Event
from app.news.news_service import NewsService


class FakeRssNewsSource:
    source_id = "fake_rss"
    source_name = "Fake RSS"

    def __init__(self, items_by_symbol: dict[str, list[dict]]) -> None:
        self._items_by_symbol = items_by_symbol
        self.fetch_calls: list[str] = []

    def fetch_ticker_news(self, symbol: str) -> list[dict]:
        self.fetch_calls.append(symbol)
        return list(self._items_by_symbol.get(symbol.upper(), []))


class RaisingNewsSource:
    source_id = "raising"
    source_name = "Raising Source"

    def fetch_ticker_news(self, symbol: str) -> list[dict]:
        raise RuntimeError("upstream blocked")


class EmptyNewsSource:
    source_id = "empty"
    source_name = "Empty Source"

    def fetch_ticker_news(self, symbol: str) -> list[dict]:
        return []


def create_test_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)

    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return engine, SessionLocal()


def test_news_service_inserts_normalized_events_with_source_url() -> None:
    _, db = create_test_session()

    now = datetime(2026, 5, 14, 12, 0, tzinfo=timezone.utc)

    source = FakeRssNewsSource(
        items_by_symbol={
            "AMD": [
                {
                    "title": "AMD reports record earnings",
                    "link": "https://example.com/amd-earnings",
                    "summary": "AMD posted record quarterly revenue.",
                    "published": now,
                },
                {
                    "title": "Analyst upgrades AMD price target",
                    "link": "https://example.com/amd-upgrade",
                    "summary": "Analyst raises price target.",
                    "published": now,
                },
            ]
        }
    )

    service = NewsService(sources=[source])
    result = service.refresh_ticker_news(db=db, symbols=["AMD"])

    assert result.events_inserted == 2
    assert result.duplicate_events == 0
    assert "AMD" in result.successful_symbols

    rows = db.query(Event).all()
    assert {row.source_url for row in rows} == {
        "https://example.com/amd-earnings",
        "https://example.com/amd-upgrade",
    }
    assert all(row.source == "fake_rss" for row in rows)
    assert all(row.symbol == "AMD" for row in rows)


def test_news_service_dedupes_on_second_refresh() -> None:
    _, db = create_test_session()

    items = [
        {
            "title": "AMD reports record earnings",
            "link": "https://example.com/amd-earnings",
            "summary": "AMD posted record quarterly revenue.",
        }
    ]
    source = FakeRssNewsSource(items_by_symbol={"AMD": items})

    service = NewsService(sources=[source])

    first = service.refresh_ticker_news(db=db, symbols=["AMD"])
    second = service.refresh_ticker_news(db=db, symbols=["AMD"])

    assert first.events_inserted == 1
    assert first.duplicate_events == 0
    assert second.events_inserted == 0
    assert second.duplicate_events == 1
    assert db.query(Event).count() == 1


def test_news_service_handles_raising_source_safely() -> None:
    _, db = create_test_session()

    service = NewsService(sources=[RaisingNewsSource()])
    result = service.refresh_ticker_news(db=db, symbols=["AMD"])

    assert result.events_inserted == 0
    assert result.failed_reasons.get("AMD:raising") == "upstream blocked"
    assert "AMD" not in result.successful_symbols


def test_news_service_empty_source_marks_freshness_missing() -> None:
    _, db = create_test_session()

    service = NewsService(sources=[EmptyNewsSource()])
    result = service.refresh_ticker_news(db=db, symbols=["AMD"])

    assert result.events_inserted == 0
    freshness = (
        db.query(DataFreshness)
        .filter(DataFreshness.data_category == "news")
        .one_or_none()
    )
    assert freshness is not None
    assert freshness.freshness_status == "MISSING"


def test_news_service_no_watchlist_marks_freshness_missing() -> None:
    _, db = create_test_session()
    service = NewsService(sources=[EmptyNewsSource()])

    result = service.refresh_ticker_news(db=db, symbols=[])

    freshness = (
        db.query(DataFreshness)
        .filter(DataFreshness.data_category == "news")
        .one_or_none()
    )
    assert freshness is not None
    assert freshness.freshness_status == "MISSING"
    assert result.requested_symbols == []


def test_news_service_loads_watchlist_symbols_from_tickers_table() -> None:
    engine, db = create_test_session()

    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO tickers "
                "(symbol, name, asset_type, market, exchange, currency, is_active) "
                "VALUES "
                "('AMD', 'Advanced Micro Devices', 'STOCK', 'US', 'NASDAQ', 'USD', 1), "
                "('NVDA', 'NVIDIA', 'STOCK', 'US', 'NASDAQ', 'USD', 1)"
            )
        )

    service = NewsService(sources=[EmptyNewsSource()])
    symbols = service.load_watchlist_symbols(db)

    assert symbols == ["AMD", "NVDA"]


def test_news_service_works_with_no_option_data() -> None:
    """Phase 9 must not depend on option data."""
    _, db = create_test_session()

    source = FakeRssNewsSource(
        items_by_symbol={
            "AMD": [
                {
                    "title": "AMD news headline",
                    "link": "https://example.com/x",
                }
            ]
        }
    )

    service = NewsService(sources=[source])
    result = service.refresh_ticker_news(db=db, symbols=["AMD"])

    assert result.events_inserted == 1
    assert db.query(Event).count() == 1
