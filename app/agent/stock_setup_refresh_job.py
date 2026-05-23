from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.agent.market_data_refresh_job import record_agent_run
from app.common.service_utils import ensure_tables
from app.quant.stock_setup_service import StockSetupService


def run_stock_setup_refresh_job(
    db: Session,
    symbols: list[str] | None = None,
    triggered_by: str = "USER",
    trigger_source: str = "API",
    stock_setup_service: StockSetupService | None = None,
) -> dict[str, Any]:
    ensure_tables(db)

    service = stock_setup_service or StockSetupService()

    try:
        result = service.refresh_stock_setups(db=db, symbols=symbols)

        if result.records_failed > 0 and result.successful_symbols:
            status = "PARTIAL_SUCCESS"
        elif result.records_failed > 0 and not result.successful_symbols:
            status = "FAILED"
        else:
            status = "SUCCESS"

        details = result.to_dict()

        agent_run_recorded = record_agent_run(
            db=db,
            job_name="stock_setup_refresh",
            job_type="STOCK_SETUP",
            status=status,
            triggered_by=triggered_by,
            trigger_source=trigger_source,
            symbols_processed=len(result.successful_symbols),
            records_created=result.records_created,
            records_updated=result.records_updated,
            records_failed=result.records_failed,
            error_message=None if status != "FAILED" else "Stock setup refresh failed.",
            details=details,
        )

        return {
            "status": status,
            "job_name": "stock_setup_refresh",
            "job_type": "STOCK_SETUP",
            "triggered_by": triggered_by,
            "trigger_source": trigger_source,
            "symbols_processed": len(result.successful_symbols),
            "records_created": result.records_created,
            "records_updated": result.records_updated,
            "records_failed": result.records_failed,
            "agent_run_recorded": agent_run_recorded,
            "result": details,
        }

    except Exception as exc:
        db.rollback()

        agent_run_recorded = record_agent_run(
            db=db,
            job_name="stock_setup_refresh",
            job_type="STOCK_SETUP",
            status="FAILED",
            triggered_by=triggered_by,
            trigger_source=trigger_source,
            symbols_processed=0,
            records_created=0,
            records_updated=0,
            records_failed=1,
            error_message=str(exc),
            details={"error": str(exc), "symbols": symbols or []},
        )

        return {
            "status": "FAILED",
            "job_name": "stock_setup_refresh",
            "job_type": "STOCK_SETUP",
            "triggered_by": triggered_by,
            "trigger_source": trigger_source,
            "symbols_processed": 0,
            "records_created": 0,
            "records_updated": 0,
            "records_failed": 1,
            "agent_run_recorded": agent_run_recorded,
            "error": str(exc),
        }
