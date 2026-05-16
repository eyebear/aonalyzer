from datetime import date, timedelta

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.database.base import Base
from app.database.models import DailyPrice
from app.quant.technical_analysis_service import (
    INSUFFICIENT_PRICE_HISTORY,
    SUFFICIENT,
    TechnicalAnalysisService,
)
from app.quant.technical_snapshot_models import TechnicalSnapshot


def create_test_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return engine, SessionLocal()


def seed_prices(
    db,
    symbol: str,
    closes: list[float],
    start_date: date | None = None,
    volume_each: float = 100.0,
) -> None:
    """Insert ``closes`` as consecutive daily price rows."""
    cursor_date = start_date or (date(2026, 1, 1) - timedelta(days=len(closes)))
    for index, close in enumerate(closes):
        row_date = cursor_date + timedelta(days=index)
        db.add(
            DailyPrice(
                symbol=symbol.upper(),
                price_date=row_date,
                open_price=close,
                high_price=close + 1.0,
                low_price=close - 1.0,
                close_price=close,
                adjusted_close_price=close,
                volume=int(volume_each),
                source="test",
            )
        )
    db.commit()


def test_insufficient_price_history_status_when_too_few_rows() -> None:
    _, db = create_test_session()

    seed_prices(db, "AMD", [100.0, 101.0, 102.0])  # only 3 rows

    service = TechnicalAnalysisService()
    result = service.compute_for_symbol(db=db, symbol="AMD")

    assert result.data_sufficiency_status == INSUFFICIENT_PRICE_HISTORY
    assert result.indicators is None
    assert result.source_record_count == 3
    assert result.reason is not None


def test_partial_status_when_only_short_indicators_can_compute() -> None:
    _, db = create_test_session()

    # 15 rows: enough for ema_12 (12), rsi_14 (15), and atr_14 (15), but not
    # enough for sma_20, sma_50, sma_200, ema_26, macd, bollinger, volume_ratio.
    closes = [100.0 + i for i in range(15)]
    seed_prices(db, "AMD", closes)

    service = TechnicalAnalysisService()
    result = service.compute_for_symbol(db=db, symbol="AMD")

    assert result.indicators is not None
    assert result.data_sufficiency_status == "PARTIAL"
    insufficient = set(result.indicators.insufficient_indicators)
    assert "sma_20" in insufficient
    assert "sma_50" in insufficient
    assert "sma_200" in insufficient
    assert "ema_26" in insufficient
    assert "macd" in insufficient
    assert "bollinger_bands_20" in insufficient
    assert "volume_ratio_20" in insufficient
    # but the short ones should be present
    assert result.indicators.ema_12 is not None
    assert result.indicators.rsi_14 is not None
    assert result.indicators.atr_14 is not None


def test_sufficient_status_when_enough_history_for_all_short_indicators() -> None:
    _, db = create_test_session()

    closes = [100.0 + (i % 7) * 0.5 for i in range(60)]  # 60 rows
    seed_prices(db, "AMD", closes)

    service = TechnicalAnalysisService()
    result = service.compute_for_symbol(db=db, symbol="AMD")

    assert result.indicators is not None
    assert result.indicators.sma_20 is not None
    assert result.indicators.sma_50 is not None
    assert result.indicators.ema_12 is not None
    assert result.indicators.ema_26 is not None
    assert result.indicators.macd is not None
    assert result.indicators.macd_signal is not None
    assert result.indicators.bollinger_middle is not None
    assert result.indicators.atr_14 is not None
    assert result.indicators.volume_ratio_20 is not None
    # sma_200 still insufficient (need 200 rows)
    assert "sma_200" in result.indicators.insufficient_indicators
    # status is PARTIAL because sma_200 is missing
    assert result.data_sufficiency_status == "PARTIAL"


def test_full_sufficiency_when_history_exceeds_all_thresholds() -> None:
    _, db = create_test_session()

    closes = [100.0 + (i % 11) * 0.25 for i in range(220)]
    seed_prices(db, "AMD", closes)

    service = TechnicalAnalysisService()
    result = service.compute_for_symbol(db=db, symbol="AMD")

    assert result.indicators is not None
    assert result.indicators.sma_200 is not None
    assert result.data_sufficiency_status == SUFFICIENT
    assert result.indicators.insufficient_indicators == []


def test_persist_snapshot_upserts_per_symbol_and_date() -> None:
    _, db = create_test_session()

    closes = [100.0 + i * 0.5 for i in range(60)]
    seed_prices(db, "AMD", closes)

    service = TechnicalAnalysisService()
    first = service.compute_for_symbol(db=db, symbol="AMD")
    row1, inserted_first = service.persist_snapshot(db=db, result=first)
    db.commit()

    second = service.compute_for_symbol(db=db, symbol="AMD")
    row2, inserted_second = service.persist_snapshot(db=db, result=second)
    db.commit()

    assert inserted_first is True
    assert inserted_second is False
    assert row1.id == row2.id
    assert db.query(TechnicalSnapshot).count() == 1


def test_refresh_technical_snapshots_handles_mixed_history_across_symbols() -> None:
    engine, db = create_test_session()

    # Seed watchlist symbols.
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO tickers "
                "(symbol, name, asset_type, market, exchange, currency, is_active) "
                "VALUES "
                "('AMD', 'AMD', 'STOCK', 'US', 'NASDAQ', 'USD', 1), "
                "('NVDA', 'NVDA', 'STOCK', 'US', 'NASDAQ', 'USD', 1), "
                "('NEW', 'New IPO', 'STOCK', 'US', 'NASDAQ', 'USD', 1)"
            )
        )

    seed_prices(db, "AMD", [100.0 + i * 0.5 for i in range(60)])
    seed_prices(db, "NVDA", [200.0 + i * 0.3 for i in range(60)])
    seed_prices(db, "NEW", [50.0, 51.0, 52.0])  # too few

    service = TechnicalAnalysisService()
    result = service.refresh_technical_snapshots(db=db)

    assert set(result.requested_symbols) == {"AMD", "NVDA", "NEW"}
    assert set(result.successful_symbols) == {"AMD", "NVDA"}
    assert "NEW" in result.insufficient_symbols
    assert result.snapshots_inserted == 2
    assert db.query(TechnicalSnapshot).count() == 2


def test_refresh_technical_snapshots_does_not_touch_option_tables() -> None:
    """Phase 11 must not depend on option data."""
    engine, db = create_test_session()

    # Confirm the option-side tables do not exist in this in-memory DB.
    table_names = {
        row[0]
        for row in db.execute(
            text("SELECT name FROM sqlite_master WHERE type='table'")
        )
    }
    assert "manual_option_snapshots" not in table_names
    assert "option_chain_snapshots" not in table_names

    seed_prices(db, "AMD", [100.0 + i * 0.3 for i in range(60)])

    service = TechnicalAnalysisService()
    result = service.refresh_technical_snapshots(db=db, symbols=["AMD"])

    assert "AMD" in result.successful_symbols
    assert db.query(TechnicalSnapshot).count() == 1


def test_refresh_with_no_symbols_returns_clean_empty_result() -> None:
    _, db = create_test_session()

    service = TechnicalAnalysisService()
    result = service.refresh_technical_snapshots(db=db, symbols=[])

    assert result.requested_symbols == []
    assert result.snapshots_inserted == 0
    assert result.successful_symbols == []
    assert result.insufficient_symbols == []
    assert result.failed_symbols == []
