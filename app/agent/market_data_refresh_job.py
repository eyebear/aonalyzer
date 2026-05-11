from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

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


def record_agent_run(
    db: Session,
    job_name: str,
    job_type: str,
    status: str,
    triggered_by: str,
    trigger_source: str,
    symbols_processed: int,
    records_created: int,
    records_updated: int,
    records_failed: int,
    error_message: str | None,
    details: dict[str, Any],
) -> bool:
    inspector = inspect(db.get_bind())

    if "agent_runs" not in inspector.get_table_names():
        return False

    table_columns = {
        column["name"]
        for column in inspector.get_columns("agent_runs")
    }

    now = datetime.now(timezone.utc)

    candidate_values: dict[str, Any] = {
        "job_name": job_name,
        "job_type": job_type,
        "status": status,
        "triggered_by": triggered_by,
        "trigger_source": trigger_source,
        "symbols_processed": symbols_processed,
        "records_created": records_created,
        "records_updated": records_updated,
        "records_failed": records_failed,
        "error_message": error_message,
        "message": error_message,
        "details_json": details,
        "result_json": details,
        "started_at": now,
        "finished_at": now,
        "completed_at": now,
        "created_at": now,
        "updated_at": now,
    }

    insert_values = {
        key: value
        for key, value in candidate_values.items()
        if key in table_columns
    }

    required_fallbacks = {
        "job_name": job_name,
        "job_type": job_type,
        "status": status,
        "triggered_by": triggered_by,
        "trigger_source": trigger_source,
        "symbols_processed": symbols_processed,
        "records_created": records_created,
        "records_updated": records_updated,
        "records_failed": records_failed,
        "started_at": now,
        "finished_at": now,
    }

    for key, value in required_fallbacks.items():
        if key in table_columns and key not in insert_values:
            insert_values[key] = value

    if not insert_values:
        return False

    column_sql = ", ".join(insert_values.keys())
    value_sql = ", ".join(f":{key}" for key in insert_values.keys())

    try:
        db.execute(
            text(f"INSERT INTO agent_runs ({column_sql}) VALUES ({value_sql})"),
            insert_values,
        )
        db.commit()
        return True
    except Exception:
        db.rollback()
        return False