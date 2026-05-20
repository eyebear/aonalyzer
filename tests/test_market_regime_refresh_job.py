from datetime import date, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.agent.market_regime_refresh_job import run_market_regime_refresh_job
from app.core.config import AppSettings
from app.database.base import Base
from app.database.models import AgentRun, DailyPrice
from app.market_regime.market_regime_models import MarketRegimeSnapshot
from app.market_regime.market_regime_service import MarketRegimeService


def create_test_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return engine, SessionLocal()


def _settings() -> AppSettings:
    return AppSettings(
        market_regime_sector_etfs=["XLK", "XLF"],
        market_regime_benchmark_symbols=["SPY"],
        market_regime_trend_fast_period=2,
        market_regime_trend_slow_period=3,
        market_regime_rs_lookback_days=2,
        market_regime_min_price_rows=3,
    )


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


def test_refresh_job_records_success_and_agent_run() -> None:
    _, db = create_test_session()
    _seed_closes(db, "SPY", [100.0, 101.0, 102.0, 103.0, 104.0, 105.0])
    _seed_closes(db, "QQQ", [200.0, 202.0, 204.0, 206.0, 208.0, 210.0])
    _seed_closes(db, "IWM", [50.0, 51.0, 52.0, 53.0, 54.0, 55.0])
    _seed_closes(db, "^VIX", [12.0, 12.0, 12.0])
    _seed_closes(db, "^TNX", [4.0, 4.0, 4.0])
    _seed_closes(db, "XLK", [100.0, 110.0, 121.0])
    _seed_closes(db, "XLF", [100.0, 100.0, 100.0])

    service = MarketRegimeService(settings=_settings())
    response = run_market_regime_refresh_job(db=db, market_regime_service=service)

    assert response["status"] == "SUCCESS"
    assert response["job_name"] == "market_regime_refresh"
    assert response["records_created"] >= 1
    assert response["agent_run_recorded"] is True

    assert db.query(MarketRegimeSnapshot).count() == 1
    run = (
        db.query(AgentRun)
        .filter(AgentRun.job_name == "market_regime_refresh")
        .one()
    )
    assert run.job_type == "MARKET_REGIME"
    assert run.status == "SUCCESS"


def test_refresh_job_failed_status_when_no_data() -> None:
    _, db = create_test_session()

    service = MarketRegimeService(settings=_settings())
    response = run_market_regime_refresh_job(db=db, market_regime_service=service)

    # No price rows at all → no snapshot produced; recorded as a FAILED job run
    # but this is non-blocking context, not an exception.
    assert response["status"] == "FAILED"
    assert response["records_created"] == 0
    assert db.query(MarketRegimeSnapshot).count() == 0
    run = (
        db.query(AgentRun)
        .filter(AgentRun.job_name == "market_regime_refresh")
        .one()
    )
    assert run.status == "FAILED"
