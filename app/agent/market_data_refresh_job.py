from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.agent.agent_run_recorder import record_agent_run
from app.database.base import Base
from app.database.connection import engine
from app.market_data.market_data_service import MarketDataService


def run_market_data_refresh_job(
    db: Session,
    symbols: list[str] | None = None,
    triggered_by: str = "USER",
    trigger_source: str = "API",
    include_daily: bool = True,
    include_intraday: bool = True,
    daily_period: str = "6mo",
    intraday_period: str = "1d",
    intraday_interval: str = "5m",
) -> dict[str, Any]:
    Base.metadata.create_all(bind=engine)

    service = MarketDataService()

    try:
        result = service.refresh_market_data(
            db=db,
            symbols=symbols,
            include_daily=include_daily,
            include_intraday=include_intraday,
            daily_period=daily_period,
            intraday_period=intraday_period,
            intraday_interval=intraday_interval,
        )

        if result.successful_symbols and result.failed_symbols:
            status = "PARTIAL_SUCCESS"
        elif result.successful_symbols:
            status = "SUCCESS"
        else:
            status = "FAILED"

        details = result.to_dict()

        agent_run_recorded = record_agent_run(
            db=db,
            job_name="market_data_refresh",
            job_type="MARKET_DATA",
            status=status,
            triggered_by=triggered_by,
            trigger_source=trigger_source,
            symbols_processed=len(result.successful_symbols),
            records_created=result.records_created,
            records_updated=result.records_updated,
            records_failed=len(result.failed_symbols),
            error_message=None if status != "FAILED" else "No market data was fetched.",
            details=details,
        )

        return {
            "status": status,
            "job_name": "market_data_refresh",
            "job_type": "MARKET_DATA",
            "triggered_by": triggered_by,
            "trigger_source": trigger_source,
            "symbols_processed": len(result.successful_symbols),
            "records_created": result.records_created,
            "records_updated": result.records_updated,
            "records_failed": len(result.failed_symbols),
            "agent_run_recorded": agent_run_recorded,
            "result": details,
        }

    except Exception as exc:
        db.rollback()

        agent_run_recorded = record_agent_run(
            db=db,
            job_name="market_data_refresh",
            job_type="MARKET_DATA",
            status="FAILED",
            triggered_by=triggered_by,
            trigger_source=trigger_source,
            symbols_processed=0,
            records_created=0,
            records_updated=0,
            records_failed=1,
            error_message=str(exc),
            details={
                "error": str(exc),
                "symbols": symbols or [],
            },
        )

        return {
            "status": "FAILED",
            "job_name": "market_data_refresh",
            "job_type": "MARKET_DATA",
            "triggered_by": triggered_by,
            "trigger_source": trigger_source,
            "symbols_processed": 0,
            "records_created": 0,
            "records_updated": 0,
            "records_failed": 1,
            "agent_run_recorded": agent_run_recorded,
            "error": str(exc),
        }


# ``record_agent_run`` now lives in ``app.agent.agent_run_recorder``. It is
# re-exported here so existing ``from app.agent.market_data_refresh_job import
# record_agent_run`` call sites keep working unchanged.
__all__ = ["record_agent_run", "run_market_data_refresh_job"]