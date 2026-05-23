from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.agent.setup_detection_refresh_job import run_setup_detection_refresh_job
from app.core.config import AppSettings
from app.database.base import Base
from app.database.models import AgentRun
from app.market_regime.market_regime_models import MarketRegimeSnapshot
from app.quant.stock_setup_models import StockSetup
from app.quant.technical_snapshot_models import TechnicalSnapshot
from app.setup_detection.setup_detection_models import StockSetupSignal
from app.setup_detection.setup_detection_service import SetupDetectionService

D = date(2026, 5, 15)


def create_test_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return engine, SessionLocal()


def test_refresh_job_records_success_and_agent_run() -> None:
    _, db = create_test_session()
    db.add(
        TechnicalSnapshot(
            symbol="AMD",
            snapshot_date=D,
            source="test",
            source_record_count=200,
            last_close=104.0,
            sma_20=105.0,
            sma_50=100.0,
            sma_200=90.0,
            rsi_14=45.0,
            atr_14=4.0,
            volume_ratio_20=1.5,
            data_sufficiency_status="SUFFICIENT",
            insufficient_indicators_json=[],
        )
    )
    db.add(
        StockSetup(
            symbol="AMD",
            snapshot_date=D,
            source="daily_prices+technical",
            source_record_count=120,
            current_close=104.0,
            stock_risk_reward=3.0,
            data_sufficiency_status="SUFFICIENT",
            insufficient_reasons_json=[],
        )
    )
    db.add(MarketRegimeSnapshot(snapshot_date=D, regime_label="RISK_ON"))
    db.commit()

    service = SetupDetectionService(settings=AppSettings())
    response = run_setup_detection_refresh_job(
        db=db, symbols=["AMD"], setup_detection_service=service
    )

    assert response["status"] == "SUCCESS"
    assert response["job_name"] == "setup_detection_refresh"
    assert response["records_created"] == 1
    assert response["agent_run_recorded"] is True

    assert db.query(StockSetupSignal).count() == 1
    run = db.query(AgentRun).filter(AgentRun.job_name == "setup_detection_refresh").one()
    assert run.job_type == "SETUP_DETECTION"
    assert run.status == "SUCCESS"


def test_refresh_job_success_with_no_symbols() -> None:
    _, db = create_test_session()
    # No watchlist, no symbols -> empty but successful run (non-blocking).
    service = SetupDetectionService(settings=AppSettings())
    response = run_setup_detection_refresh_job(db=db, symbols=[], setup_detection_service=service)

    assert response["status"] == "SUCCESS"
    assert response["records_created"] == 0
    assert db.query(StockSetupSignal).count() == 0
