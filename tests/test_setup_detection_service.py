from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import AppSettings
from app.database.base import Base
from app.market_regime.market_regime_models import (
    MarketRegimeSnapshot,
    SectorStrengthSnapshot,
)
from app.quant.stock_setup_models import StockSetup
from app.quant.technical_snapshot_models import TechnicalSnapshot
from app.setup_detection.setup_detection_models import StockSetupSignal
from app.setup_detection.setup_detection_service import (
    PARTIAL,
    SUFFICIENT,
    SetupDetectionService,
)

D = date(2026, 5, 15)


def create_test_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return engine, SessionLocal()


def _seed_technical(
    db,
    symbol,
    *,
    last_close,
    sma_20,
    sma_50,
    sma_200=None,
    rsi_14=None,
    atr_14=None,
    volume_ratio_20=None,
    macd_histogram=None,
    bollinger_lower=None,
    snapshot_date=D,
) -> None:
    db.add(
        TechnicalSnapshot(
            symbol=symbol.upper(),
            snapshot_date=snapshot_date,
            source="test",
            source_record_count=200,
            last_close=last_close,
            sma_20=sma_20,
            sma_50=sma_50,
            sma_200=sma_200,
            rsi_14=rsi_14,
            macd_histogram=macd_histogram,
            atr_14=atr_14,
            bollinger_lower=bollinger_lower,
            volume_ratio_20=volume_ratio_20,
            data_sufficiency_status="SUFFICIENT",
            insufficient_indicators_json=[],
        )
    )
    db.commit()


def _seed_setup(
    db,
    symbol,
    *,
    current_close,
    nearest_support=None,
    nearest_resistance=None,
    stock_risk_reward=None,
    target_price=None,
    stop_price=None,
    snapshot_date=D,
) -> None:
    db.add(
        StockSetup(
            symbol=symbol.upper(),
            snapshot_date=snapshot_date,
            source="daily_prices+technical",
            source_record_count=120,
            current_close=current_close,
            nearest_support=nearest_support,
            nearest_resistance=nearest_resistance,
            stock_risk_reward=stock_risk_reward,
            target_price=target_price,
            stop_price=stop_price,
            data_sufficiency_status="SUFFICIENT",
            insufficient_reasons_json=[],
        )
    )
    db.commit()


def _seed_regime(db, label="RISK_ON", snapshot_date=D) -> None:
    db.add(MarketRegimeSnapshot(snapshot_date=snapshot_date, regime_label=label))
    db.commit()


def test_detect_pullback_long_persists_signal() -> None:
    _, db = create_test_session()
    _seed_technical(
        db,
        "AMD",
        last_close=104.0,
        sma_20=105.0,
        sma_50=100.0,
        sma_200=90.0,
        rsi_14=45.0,
        atr_14=4.0,
        volume_ratio_20=1.5,
    )
    _seed_setup(
        db,
        "AMD",
        current_close=104.0,
        nearest_resistance=None,
        stock_risk_reward=3.0,
        target_price=120.0,
        stop_price=98.0,
    )
    _seed_regime(db, "RISK_ON")

    service = SetupDetectionService(settings=AppSettings())
    computation = service.detect_for_symbol(db, "AMD")

    assert computation.result.setup_type == "PULLBACK_LONG"
    assert computation.result.direction == "LONG"
    assert computation.data_sufficiency_status == SUFFICIENT
    assert computation.result.score == 85

    result = service.refresh_setup_signals(db, symbols=["AMD"])
    assert "AMD" in result.successful_symbols
    assert result.signals_inserted == 1

    signal = db.query(StockSetupSignal).one()
    assert signal.setup_type == "PULLBACK_LONG"
    assert signal.target_price == 120.0


def test_partial_when_setup_math_missing() -> None:
    _, db = create_test_session()
    # Technical present (pullback shape), but no Phase 12 StockSetup row.
    _seed_technical(
        db,
        "AMD",
        last_close=104.0,
        sma_20=105.0,
        sma_50=100.0,
        sma_200=90.0,
        rsi_14=45.0,
        atr_14=4.0,
    )
    _seed_regime(db, "RISK_ON")

    service = SetupDetectionService(settings=AppSettings())
    computation = service.detect_for_symbol(db, "AMD")

    assert computation.result.setup_type == "PULLBACK_LONG"
    assert computation.data_sufficiency_status == PARTIAL
    assert computation.risk_reward is None


def test_insufficient_when_no_technical() -> None:
    _, db = create_test_session()
    _seed_setup(db, "AMD", current_close=104.0, stock_risk_reward=3.0)

    service = SetupDetectionService(settings=AppSettings())
    result = service.refresh_setup_signals(db, symbols=["AMD"])

    assert "AMD" in result.insufficient_symbols
    signal = db.query(StockSetupSignal).one()
    assert signal.setup_type == "NO_TRADE"
    assert signal.data_sufficiency_status == "INSUFFICIENT_INPUT"


def test_sector_strength_long_with_sector_map() -> None:
    _, db = create_test_session()
    # Uptrend but neither pullback (rsi 60) nor breakout (no resistance).
    _seed_technical(
        db,
        "NVDA",
        last_close=120.0,
        sma_20=105.0,
        sma_50=100.0,
        sma_200=90.0,
        rsi_14=60.0,
        atr_14=4.0,
    )
    _seed_setup(db, "NVDA", current_close=120.0, nearest_resistance=None)
    _seed_regime(db, "RISK_ON")
    db.add(
        SectorStrengthSnapshot(
            snapshot_date=D,
            sector_symbol="SMH",
            benchmark_symbol="SPY",
            trend="OUTPERFORM",
            rs_rank=1,
            lookback_days=20,
        )
    )
    db.commit()

    settings = AppSettings(
        setup_sector_map={"NVDA": "SMH"},
        market_regime_benchmark_symbols=["SPY"],
    )
    service = SetupDetectionService(settings=settings)
    computation = service.detect_for_symbol(db, "NVDA")

    assert computation.result.setup_type == "SECTOR_STRENGTH_LONG"
    assert computation.sector_symbol == "SMH"
    assert computation.sector_trend == "OUTPERFORM"


def test_refresh_is_idempotent_per_symbol_date() -> None:
    _, db = create_test_session()
    _seed_technical(
        db,
        "AMD",
        last_close=104.0,
        sma_20=105.0,
        sma_50=100.0,
        sma_200=90.0,
        rsi_14=45.0,
        atr_14=4.0,
    )
    _seed_setup(db, "AMD", current_close=104.0, stock_risk_reward=3.0)
    _seed_regime(db, "RISK_ON")

    service = SetupDetectionService(settings=AppSettings())
    first = service.refresh_setup_signals(db, symbols=["AMD"])
    second = service.refresh_setup_signals(db, symbols=["AMD"])

    assert first.signals_inserted == 1
    assert second.signals_inserted == 0
    assert second.signals_updated == 1
    assert db.query(StockSetupSignal).count() == 1


def test_does_not_require_option_data() -> None:
    _, db = create_test_session()
    from sqlalchemy import inspect

    assert "manual_option_snapshots" not in set(inspect(db.get_bind()).get_table_names())

    _seed_technical(
        db,
        "AMD",
        last_close=104.0,
        sma_20=105.0,
        sma_50=100.0,
        sma_200=90.0,
        rsi_14=45.0,
        atr_14=4.0,
    )
    _seed_setup(db, "AMD", current_close=104.0, stock_risk_reward=3.0)

    service = SetupDetectionService(settings=AppSettings())
    result = service.refresh_setup_signals(db, symbols=["AMD"])
    assert "AMD" in result.successful_symbols
