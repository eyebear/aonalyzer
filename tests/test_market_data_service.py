from datetime import date, datetime, timezone

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.data_quality.data_quality_models import DataFreshness
from app.database.base import Base
from app.market_data.market_data_models import (
    DailyPrice,
    FailedTickerLog,
    IntradayPrice,
)
from app.market_data.market_data_service import (
    MarketDataService,
    OHLCVRow,
)


class FakeMarketDataClient:
    def fetch_daily_ohlcv(
        self,
        symbol: str,
        period: str = "6mo",
    ) -> list[OHLCVRow]:
        return [
            OHLCVRow(
                symbol=symbol,
                timestamp=date(2026, 5, 8),
                open_price=100.0,
                high_price=110.0,
                low_price=95.0,
                close_price=108.0,
                adjusted_close=108.0,
                volume=1000000.0,
            ),
            OHLCVRow(
                symbol=symbol,
                timestamp=date(2026, 5, 9),
                open_price=108.0,
                high_price=112.0,
                low_price=104.0,
                close_price=110.0,
                adjusted_close=110.0,
                volume=1200000.0,
            ),
        ]

    def fetch_intraday_ohlcv(
        self,
        symbol: str,
        period: str = "1d",
        interval: str = "5m",
    ) -> list[OHLCVRow]:
        return [
            OHLCVRow(
                symbol=symbol,
                timestamp=datetime(2026, 5, 11, 13, 30, tzinfo=timezone.utc),
                open_price=110.0,
                high_price=111.0,
                low_price=109.5,
                close_price=110.5,
                adjusted_close=None,
                volume=50000.0,
            )
        ]


class FailingMarketDataClient:
    def fetch_daily_ohlcv(
        self,
        symbol: str,
        period: str = "6mo",
    ) -> list[OHLCVRow]:
        raise RuntimeError("source failed")

    def fetch_intraday_ohlcv(
        self,
        symbol: str,
        period: str = "1d",
        interval: str = "5m",
    ) -> list[OHLCVRow]:
        raise RuntimeError("source failed")


def create_test_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)

    TestingSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine,
    )

    return engine, TestingSessionLocal()


def test_market_data_refresh_stores_daily_and_intraday_prices() -> None:
    _, db = create_test_session()

    service = MarketDataService(client=FakeMarketDataClient())

    result = service.refresh_market_data(
        db=db,
        symbols=["AMD"],
        include_daily=True,
        include_intraday=True,
    )

    daily_count = db.query(DailyPrice).count()
    intraday_count = db.query(IntradayPrice).count()
    freshness = (
        db.query(DataFreshness)
        .filter(DataFreshness.data_category == "market_data")
        .one_or_none()
    )

    assert result.successful_symbols == ["AMD"]
    assert result.daily_rows_inserted == 2
    assert result.intraday_rows_inserted == 1
    assert daily_count == 2
    assert intraday_count == 1
    assert freshness is not None
    assert freshness.freshness_status == "FRESH"


def test_market_data_refresh_updates_existing_rows_instead_of_duplicating() -> None:
    _, db = create_test_session()

    service = MarketDataService(client=FakeMarketDataClient())

    first_result = service.refresh_market_data(
        db=db,
        symbols=["AMD"],
        include_daily=True,
        include_intraday=True,
    )

    second_result = service.refresh_market_data(
        db=db,
        symbols=["AMD"],
        include_daily=True,
        include_intraday=True,
    )

    daily_count = db.query(DailyPrice).count()
    intraday_count = db.query(IntradayPrice).count()

    assert first_result.daily_rows_inserted == 2
    assert first_result.intraday_rows_inserted == 1
    assert second_result.daily_rows_inserted == 0
    assert second_result.daily_rows_updated == 2
    assert second_result.intraday_rows_inserted == 0
    assert second_result.intraday_rows_updated == 1
    assert daily_count == 2
    assert intraday_count == 1


def test_load_watchlist_symbols_from_database() -> None:
    engine, db = create_test_session()

    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO tickers "
                "(symbol, name, asset_type, market, exchange, currency, is_active) "
                "VALUES "
                "('AMD', 'Advanced Micro Devices', 'STOCK', 'US', 'NASDAQ', 'USD', 1), "
                "('NVDA', 'NVIDIA', 'STOCK', 'US', 'NASDAQ', 'USD', 1), "
                "('OLD', 'Old Disabled Ticker', 'STOCK', 'US', 'NASDAQ', 'USD', 0)"
            )
        )

    service = MarketDataService(client=FakeMarketDataClient())

    symbols = service.load_watchlist_symbols(db)

    assert symbols == ["AMD", "NVDA"]


def test_failed_ticker_is_logged_when_source_fails() -> None:
    _, db = create_test_session()

    service = MarketDataService(client=FailingMarketDataClient())

    result = service.refresh_market_data(
        db=db,
        symbols=["BAD"],
        include_daily=True,
        include_intraday=False,
    )

    failed_logs = db.query(FailedTickerLog).all()

    assert result.successful_symbols == []
    assert result.failed_symbols == ["BAD"]
    assert len(failed_logs) == 1
    assert failed_logs[0].symbol == "BAD"
    assert failed_logs[0].data_category == "market_data"
    assert "source failed" in failed_logs[0].reason


def test_market_data_refresh_with_empty_watchlist_marks_freshness_missing() -> None:
    _, db = create_test_session()

    service = MarketDataService(client=FakeMarketDataClient())

    result = service.refresh_market_data(
        db=db,
        symbols=[],
        include_daily=True,
        include_intraday=True,
    )

    freshness = (
        db.query(DataFreshness)
        .filter(DataFreshness.data_category == "market_data")
        .one_or_none()
    )

    assert result.requested_symbols == []
    assert result.records_created == 0
    assert freshness is not None
    assert freshness.freshness_status == "MISSING"