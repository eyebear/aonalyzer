from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.data_quality.data_quality_models import DataFreshness
from app.database.base import Base
from app.earnings.earnings_calendar_service import EarningsCalendarService
from app.earnings.earnings_models import EarningsEvent


class FakeEarningsCalendarSource:
    source_id = "fake_calendar"
    source_name = "Fake Earnings"

    def __init__(self, items_by_symbol: dict[str, list[dict]]) -> None:
        self._items_by_symbol = items_by_symbol
        self.fetch_calls: list[str] = []

    def fetch_ticker_earnings(self, symbol: str) -> list[dict]:
        self.fetch_calls.append(symbol)
        return list(self._items_by_symbol.get(symbol.upper(), []))


class RaisingEarningsSource:
    source_id = "raising"
    source_name = "Raising"

    def fetch_ticker_earnings(self, symbol: str) -> list[dict]:
        raise RuntimeError("upstream blocked")


def create_test_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return engine, SessionLocal()


def test_inserts_normalized_event_with_source_url() -> None:
    _, db = create_test_session()

    earnings_dt = datetime(2026, 6, 12, 20, 0, tzinfo=timezone.utc)
    source = FakeEarningsCalendarSource(
        items_by_symbol={
            "AMD": [
                {
                    "earnings_datetime_utc": earnings_dt,
                    "time_of_day": "amc",
                    "confirmed": True,
                    "source_url": "https://example.com/amd-earnings",
                    "source_title": "Fake Earnings",
                }
            ]
        }
    )

    service = EarningsCalendarService(sources=[source])
    result = service.refresh_ticker_earnings(db=db, symbols=["AMD"])

    assert result.events_inserted == 1
    assert "AMD" in result.successful_symbols

    row = db.query(EarningsEvent).one()
    assert row.symbol == "AMD"
    assert row.time_of_day == "AMC"
    assert row.confirmed is True
    assert row.source_url == "https://example.com/amd-earnings"


def test_dedupes_repeat_runs_for_same_symbol_datetime_source() -> None:
    _, db = create_test_session()

    item = {
        "earnings_datetime_utc": datetime(2026, 6, 12, 20, 0, tzinfo=timezone.utc),
        "time_of_day": "AMC",
    }
    source = FakeEarningsCalendarSource(items_by_symbol={"AMD": [item]})
    service = EarningsCalendarService(sources=[source])

    first = service.refresh_ticker_earnings(db=db, symbols=["AMD"])
    second = service.refresh_ticker_earnings(db=db, symbols=["AMD"])

    assert first.events_inserted == 1
    assert second.events_inserted == 0
    assert second.events_updated == 1
    assert db.query(EarningsEvent).count() == 1


def test_raising_source_is_isolated() -> None:
    _, db = create_test_session()

    service = EarningsCalendarService(sources=[RaisingEarningsSource()])
    result = service.refresh_ticker_earnings(db=db, symbols=["AMD"])

    assert result.events_inserted == 0
    assert result.failed_reasons.get("AMD:raising") == "upstream blocked"


def test_empty_symbols_marks_freshness_missing() -> None:
    _, db = create_test_session()

    service = EarningsCalendarService(sources=[FakeEarningsCalendarSource({})])
    service.refresh_ticker_earnings(db=db, symbols=[])

    freshness = (
        db.query(DataFreshness)
        .filter(DataFreshness.data_category == "earnings_calendar")
        .one_or_none()
    )
    assert freshness is not None
    assert freshness.freshness_status == "MISSING"


def test_event_with_invalid_datetime_is_rejected() -> None:
    _, db = create_test_session()

    source = FakeEarningsCalendarSource(
        items_by_symbol={
            "AMD": [{"earnings_datetime_utc": "not-a-date"}]
        }
    )
    service = EarningsCalendarService(sources=[source])

    result = service.refresh_ticker_earnings(db=db, symbols=["AMD"])
    assert result.events_inserted == 0
    assert result.rejected_items == 1
