from datetime import date, timedelta

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from app.database.base import Base
from app.database.models import DailyPrice
from app.quant.stock_setup_models import StockSetup
from app.quant.stock_setup_service import (
    INSUFFICIENT_PRICE_HISTORY,
    INSUFFICIENT_SETUP_DATA,
    PARTIAL,
    SUFFICIENT,
    StockSetupService,
)
from app.quant.technical_snapshot_models import TechnicalSnapshot


def create_test_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return engine, SessionLocal()


def _seed_prices(db, symbol: str, ohlcv_series: list[tuple[float, float, float, float]]) -> None:
    """ohlcv_series is a list of (open, high, low, close) tuples; one per day."""
    cursor = date(2026, 1, 1) - timedelta(days=len(ohlcv_series))
    for index, (open_p, high_p, low_p, close_p) in enumerate(ohlcv_series):
        db.add(
            DailyPrice(
                symbol=symbol.upper(),
                price_date=cursor + timedelta(days=index),
                open_price=open_p,
                high_price=high_p,
                low_price=low_p,
                close_price=close_p,
                adjusted_close_price=close_p,
                volume=100_000,
                source="test",
            )
        )
    db.commit()


def _seed_technical_snapshot(
    db,
    symbol: str,
    snapshot_date: date,
    *,
    sma_20: float | None = None,
    sma_50: float | None = None,
    sma_200: float | None = None,
    atr_14: float | None = None,
) -> None:
    db.add(
        TechnicalSnapshot(
            symbol=symbol.upper(),
            snapshot_date=snapshot_date,
            source="test",
            source_record_count=200,
            last_close=None,
            last_volume=None,
            sma_20=sma_20,
            sma_50=sma_50,
            sma_200=sma_200,
            ema_12=None,
            ema_26=None,
            rsi_14=None,
            macd=None,
            macd_signal=None,
            macd_histogram=None,
            atr_14=atr_14,
            bollinger_upper=None,
            bollinger_middle=None,
            bollinger_lower=None,
            volume_ratio_20=None,
            data_sufficiency_status="SUFFICIENT",
            insufficient_indicators_json=[],
        )
    )
    db.commit()


def test_insufficient_price_history_when_too_few_rows() -> None:
    _, db = create_test_session()
    _seed_prices(
        db,
        "AMD",
        [(10.0, 11.0, 9.0, 10.5), (10.5, 11.5, 9.5, 11.0)],
    )

    service = StockSetupService(swing_window=2)
    result = service.compute_for_symbol(db=db, symbol="AMD")

    assert result.data_sufficiency_status == INSUFFICIENT_PRICE_HISTORY
    assert result.setup is None
    assert result.source_record_count == 2


def test_setup_uses_atr_stop_when_technical_snapshot_has_atr() -> None:
    _, db = create_test_session()

    # 15-row series with swing low (95) at index 5 and swing high (110) at
    # index 10. Final row is the "current" close at 100. Both swings have
    # at least window=2 rows of context on each side.
    series = [
        (100.0, 101.0, 98.0, 100.0),   # 0
        (100.0, 100.0, 97.0, 99.0),    # 1
        (99.0, 99.0, 96.0, 98.0),      # 2
        (98.0, 98.0, 97.0, 97.5),      # 3
        (97.5, 97.0, 96.0, 96.5),      # 4
        (96.5, 96.0, 95.0, 95.5),      # 5  swing low (low=95)
        (95.5, 97.0, 96.0, 96.5),      # 6
        (96.5, 99.0, 96.5, 98.5),      # 7
        (98.5, 101.0, 97.0, 100.0),    # 8
        (100.0, 104.0, 99.0, 102.0),   # 9
        (102.0, 110.0, 100.0, 108.0),  # 10 swing high (high=110)
        (108.0, 109.0, 105.0, 106.0),  # 11
        (106.0, 107.0, 103.0, 104.0),  # 12
        (104.0, 105.0, 101.0, 102.0),  # 13
        (102.0, 103.0, 99.0, 100.0),   # 14 current close = 100
    ]
    _seed_prices(db, "AMD", series)

    snapshot_date = (
        db.query(DailyPrice).order_by(DailyPrice.price_date.desc()).first().price_date
    )
    _seed_technical_snapshot(
        db,
        "AMD",
        snapshot_date,
        sma_20=99.0,
        sma_50=98.0,
        sma_200=95.0,
        atr_14=2.0,
    )

    service = StockSetupService(swing_window=2)
    result = service.compute_for_symbol(db=db, symbol="AMD")

    assert result.setup is not None
    assert result.levels is not None
    assert result.current_close == 100.0
    assert result.levels.swing_low == 95.0
    assert result.levels.swing_high == 110.0
    # nearest_support = max(swing_low=95, sma_20=99, sma_50=98, sma_200=95) = 99
    assert result.levels.nearest_support == 99.0
    assert result.levels.nearest_resistance == 110.0
    # ATR stop: 100 - 1.5*2 = 97
    assert result.setup.stop_method == "ATR_1_5X"
    assert result.setup.stop_price == 97.0
    assert result.setup.target_price == 110.0
    assert result.setup.risk_per_share == 3.0
    assert result.setup.reward_per_share == 10.0
    assert result.data_sufficiency_status in {SUFFICIENT, PARTIAL}


def test_setup_falls_back_to_swing_low_buffer_without_atr() -> None:
    _, db = create_test_session()

    series = [
        (100.0, 101.0, 98.0, 100.0),
        (100.0, 100.0, 97.0, 99.0),
        (99.0, 99.0, 96.0, 98.0),
        (98.0, 98.0, 97.0, 97.5),
        (97.5, 97.0, 96.0, 96.5),
        (96.5, 96.0, 95.0, 95.5),
        (95.5, 97.0, 96.0, 96.5),
        (96.5, 99.0, 96.5, 98.5),
        (98.5, 101.0, 97.0, 100.0),
        (100.0, 104.0, 99.0, 102.0),
        (102.0, 110.0, 100.0, 108.0),
        (108.0, 109.0, 105.0, 106.0),
        (106.0, 107.0, 103.0, 104.0),
        (104.0, 105.0, 101.0, 102.0),
        (102.0, 103.0, 99.0, 100.0),
    ]
    _seed_prices(db, "AMD", series)

    service = StockSetupService(swing_window=2)
    result = service.compute_for_symbol(db=db, symbol="AMD")

    assert result.setup is not None
    assert result.setup.stop_method == "SWING_LOW_BUFFER"
    # nearest_support = swing_low (95) since no SMA cached.
    # stop = 95 * (1 - 0.02) = 93.1
    assert result.setup.stop_price is not None
    assert abs(result.setup.stop_price - 93.1) < 1e-9


def test_insufficient_setup_data_when_no_swings_present() -> None:
    """If price history is just enough for swing detection but no swing
    is found below the current close, status falls back cleanly."""
    _, db = create_test_session()

    # 12 rows, monotonically increasing → no swing low below current price.
    series = [(100.0 + i, 101.0 + i, 99.5 + i, 100.5 + i) for i in range(12)]
    _seed_prices(db, "AMD", series)

    service = StockSetupService(swing_window=2)
    result = service.compute_for_symbol(db=db, symbol="AMD")

    assert result.data_sufficiency_status == INSUFFICIENT_SETUP_DATA
    assert result.levels is not None
    assert result.levels.nearest_support is None or result.levels.nearest_resistance is None


def test_refresh_upserts_setup_per_symbol_and_date() -> None:
    _, db = create_test_session()

    series = [
        (100.0, 101.0, 98.0, 100.0),
        (100.0, 100.0, 97.0, 99.0),
        (99.0, 99.0, 96.0, 98.0),
        (98.0, 98.0, 97.0, 97.5),
        (97.5, 97.0, 96.0, 96.5),
        (96.5, 96.0, 95.0, 95.5),
        (95.5, 97.0, 96.0, 96.5),
        (96.5, 99.0, 96.5, 98.5),
        (98.5, 101.0, 97.0, 100.0),
        (100.0, 104.0, 99.0, 102.0),
        (102.0, 110.0, 100.0, 108.0),
        (108.0, 109.0, 105.0, 106.0),
        (106.0, 107.0, 103.0, 104.0),
        (104.0, 105.0, 101.0, 102.0),
        (102.0, 103.0, 99.0, 100.0),
    ]
    _seed_prices(db, "AMD", series)

    service = StockSetupService(swing_window=2)
    first = service.refresh_stock_setups(db=db, symbols=["AMD"])
    second = service.refresh_stock_setups(db=db, symbols=["AMD"])

    assert first.snapshots_inserted == 1
    assert second.snapshots_inserted == 0
    assert second.snapshots_updated == 1
    assert db.query(StockSetup).count() == 1


def test_refresh_does_not_require_option_data() -> None:
    """Phase 12 independence — manual_option_snapshots is absent here."""
    _, db = create_test_session()

    inspector = inspect(db.get_bind())
    assert "manual_option_snapshots" not in inspector.get_table_names()

    _seed_prices(
        db,
        "AMD",
        [
            (100.0, 101.0, 98.0, 100.0),
            (100.0, 100.0, 97.0, 99.0),
            (99.0, 99.0, 96.0, 98.0),
            (98.0, 98.0, 97.0, 97.5),
            (97.5, 97.0, 96.0, 96.5),
            (96.5, 96.0, 95.0, 95.5),
            (95.5, 97.0, 96.0, 96.5),
            (96.5, 99.0, 96.5, 98.5),
            (98.5, 101.0, 97.0, 100.0),
            (100.0, 104.0, 99.0, 102.0),
            (102.0, 110.0, 100.0, 108.0),
            (108.0, 109.0, 105.0, 106.0),
            (106.0, 107.0, 103.0, 104.0),
            (104.0, 105.0, 101.0, 102.0),
            (102.0, 103.0, 99.0, 100.0),
        ],
    )

    service = StockSetupService(swing_window=2)
    result = service.refresh_stock_setups(db=db, symbols=["AMD"])

    assert "AMD" in result.successful_symbols
    assert db.query(StockSetup).count() == 1


def test_refresh_with_too_few_rows_persists_insufficient_status() -> None:
    _, db = create_test_session()
    _seed_prices(db, "AMD", [(10.0, 11.0, 9.0, 10.5), (10.5, 11.5, 9.5, 11.0)])

    service = StockSetupService(swing_window=2)
    result = service.refresh_stock_setups(db=db, symbols=["AMD"])

    # Not enough rows for any swing → INSUFFICIENT_PRICE_HISTORY,
    # but the snapshot row is still persisted so dashboards can render it.
    assert "AMD" in result.insufficient_symbols
    rows = db.query(StockSetup).all()
    assert len(rows) == 1
    assert rows[0].data_sufficiency_status == INSUFFICIENT_PRICE_HISTORY


def test_refresh_loads_watchlist_when_no_symbols_given() -> None:
    engine, db = create_test_session()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO tickers "
                "(symbol, name, asset_type, market, exchange, currency, is_active) "
                "VALUES ('AMD', 'AMD', 'STOCK', 'US', 'NASDAQ', 'USD', 1)"
            )
        )

    _seed_prices(
        db,
        "AMD",
        [
            (100.0, 101.0, 98.0, 100.0),
            (100.0, 100.0, 97.0, 99.0),
            (99.0, 99.0, 96.0, 98.0),
            (98.0, 98.0, 97.0, 97.5),
            (97.5, 97.0, 96.0, 96.5),
            (96.5, 96.0, 95.0, 95.5),
            (95.5, 97.0, 96.0, 96.5),
            (96.5, 99.0, 96.5, 98.5),
            (98.5, 101.0, 97.0, 100.0),
            (100.0, 104.0, 99.0, 102.0),
            (102.0, 110.0, 100.0, 108.0),
            (108.0, 109.0, 105.0, 106.0),
            (106.0, 107.0, 103.0, 104.0),
            (104.0, 105.0, 101.0, 102.0),
            (102.0, 103.0, 99.0, 100.0),
        ],
    )

    service = StockSetupService(swing_window=2)
    result = service.refresh_stock_setups(db=db)

    assert result.requested_symbols == ["AMD"]
    assert "AMD" in result.successful_symbols
