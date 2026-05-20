from datetime import date, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import AppSettings
from app.database.base import Base
from app.database.models import DailyPrice
from app.market_regime.market_regime_models import (
    MarketRegimeSnapshot,
    SectorStrengthSnapshot,
)
from app.market_regime.market_regime_service import (
    INSUFFICIENT_PRICE_HISTORY,
    PARTIAL,
    SUFFICIENT,
    MarketRegimeService,
)


def create_test_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return engine, SessionLocal()


def _regime_settings(**overrides) -> AppSettings:
    base = dict(
        market_regime_index_symbols=["SPY", "QQQ", "IWM"],
        market_regime_vix_symbol="^VIX",
        market_regime_yield_symbol="^TNX",
        market_regime_sector_etfs=["XLK", "XLF"],
        market_regime_benchmark_symbols=["SPY"],
        market_regime_trend_fast_period=2,
        market_regime_trend_slow_period=3,
        market_regime_rs_lookback_days=2,
        market_regime_min_price_rows=3,
        market_regime_vix_calm_threshold=15.0,
        market_regime_vix_stress_threshold=25.0,
        market_regime_yield_pressure_level=4.5,
        market_regime_yield_rise_pct=0.10,
    )
    base.update(overrides)
    return AppSettings(**base)


def _seed_closes(db, symbol: str, closes: list[float], end_date: date = date(2026, 5, 15)) -> None:
    start = end_date - timedelta(days=len(closes) - 1)
    for index, close in enumerate(closes):
        db.add(
            DailyPrice(
                symbol=symbol.upper(),
                price_date=start + timedelta(days=index),
                open_price=close,
                high_price=close,
                low_price=close,
                close_price=close,
                adjusted_close_price=close,
                volume=100_000,
                source="test",
            )
        )
    db.commit()


def test_refresh_produces_risk_on_regime_and_ranked_sectors() -> None:
    _, db = create_test_session()

    _seed_closes(db, "SPY", [100.0, 101.0, 102.0, 103.0, 104.0, 105.0])
    _seed_closes(db, "QQQ", [200.0, 202.0, 204.0, 206.0, 208.0, 210.0])
    _seed_closes(db, "IWM", [50.0, 51.0, 52.0, 53.0, 54.0, 55.0])
    _seed_closes(db, "^VIX", [12.0, 12.0, 12.0])
    _seed_closes(db, "^TNX", [4.0, 4.0, 4.0])
    _seed_closes(db, "XLK", [100.0, 110.0, 121.0])  # strong outperformer
    _seed_closes(db, "XLF", [100.0, 100.0, 100.0])  # flat, underperforms SPY

    service = MarketRegimeService(settings=_regime_settings())
    result = service.refresh_market_regime(db=db)

    assert result.data_sufficiency_status == SUFFICIENT
    assert result.regime_label == "RISK_ON"
    assert result.regime_inserted == 1

    snapshot = db.query(MarketRegimeSnapshot).one()
    assert snapshot.regime_label == "RISK_ON"
    assert snapshot.spy_trend == "UP"
    assert snapshot.vix_state == "CALM"
    assert snapshot.yield_pressure is False
    assert snapshot.data_sufficiency_status == SUFFICIENT

    sectors = {
        s.sector_symbol: s
        for s in db.query(SectorStrengthSnapshot).all()
    }
    assert sectors["XLK"].rs_rank == 1
    assert sectors["XLK"].trend == "OUTPERFORM"
    assert sectors["XLF"].rs_rank == 2
    assert sectors["XLF"].trend == "UNDERPERFORM"


def test_refresh_is_idempotent_per_date() -> None:
    _, db = create_test_session()
    _seed_closes(db, "SPY", [100.0, 101.0, 102.0, 103.0, 104.0, 105.0])
    _seed_closes(db, "XLK", [100.0, 110.0, 121.0])
    _seed_closes(db, "XLF", [100.0, 100.0, 100.0])

    service = MarketRegimeService(settings=_regime_settings())
    first = service.refresh_market_regime(db=db)
    second = service.refresh_market_regime(db=db)

    assert first.regime_inserted == 1
    assert second.regime_inserted == 0
    assert second.regime_updated == 1
    assert db.query(MarketRegimeSnapshot).count() == 1


def test_missing_spy_yields_insufficient_but_still_persists() -> None:
    _, db = create_test_session()
    # No SPY data at all; QQQ/IWM present so a snapshot date still exists.
    _seed_closes(db, "QQQ", [200.0, 202.0, 204.0, 206.0, 208.0, 210.0])
    _seed_closes(db, "IWM", [50.0, 51.0, 52.0, 53.0, 54.0, 55.0])

    service = MarketRegimeService(settings=_regime_settings())
    result = service.refresh_market_regime(db=db)

    assert result.data_sufficiency_status == INSUFFICIENT_PRICE_HISTORY
    snapshot = db.query(MarketRegimeSnapshot).one()
    assert snapshot.data_sufficiency_status == INSUFFICIENT_PRICE_HISTORY
    assert snapshot.spy_trend == "INSUFFICIENT"


def test_missing_vix_and_yield_is_partial_not_blocking() -> None:
    _, db = create_test_session()
    _seed_closes(db, "SPY", [100.0, 101.0, 102.0, 103.0, 104.0, 105.0])
    _seed_closes(db, "QQQ", [200.0, 202.0, 204.0, 206.0, 208.0, 210.0])
    _seed_closes(db, "IWM", [50.0, 51.0, 52.0, 53.0, 54.0, 55.0])

    service = MarketRegimeService(settings=_regime_settings())
    result = service.refresh_market_regime(db=db)

    assert result.data_sufficiency_status == PARTIAL
    snapshot = db.query(MarketRegimeSnapshot).one()
    assert snapshot.vix_state == "UNKNOWN"
    assert snapshot.yield_pressure is False
    assert snapshot.data_sufficiency_status == PARTIAL


def test_no_data_returns_cleanly_without_snapshot() -> None:
    _, db = create_test_session()

    service = MarketRegimeService(settings=_regime_settings())
    result = service.refresh_market_regime(db=db)

    assert result.snapshot_date is None
    assert result.records_created == 0
    assert "market_regime" in result.failed_reasons
    assert db.query(MarketRegimeSnapshot).count() == 0
