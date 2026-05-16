from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.agent.market_data_refresh_job import record_agent_run
from app.database.base import Base
from app.filings.filing_service import FilingService


def run_filing_refresh_job(
    db: Session,
    symbols: list[str] | None = None,
    triggered_by: str = "USER",
    trigger_source: str = "API",
    filing_service: FilingService | None = None,
) -> dict[str, Any]:
    Base.metadata.create_all(bind=db.get_bind())

    service = filing_service or FilingService()

    try:
        result = service.refresh_ticker_filings(
            db=db,
            symbols=symbols,
        )

        if result.records_created > 0:
            status = "SUCCESS"
        elif result.failed_symbols and not result.successful_symbols:
            status = "FAILED"
        else:
            status = "SUCCESS"

        details = result.to_dict()

        agent_run_recorded = record_agent_run(
            db=db,
            job_name="filing_refresh",
            job_type="FILINGS",
            status=status,
            triggered_by=triggered_by,
            trigger_source=trigger_source,
            symbols_processed=len(result.successful_symbols),
            records_created=result.records_created,
            records_updated=result.records_updated,
            records_failed=len(result.failed_symbols),
            error_message=None if status != "FAILED" else "Filing refresh failed.",
            details=details,
        )

        return {
            "status": status,
            "job_name": "filing_refresh",
            "job_type": "FILINGS",
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
            job_name="filing_refresh",
            job_type="FILINGS",
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
            "job_name": "filing_refresh",
            "job_type": "FILINGS",
            "triggered_by": triggered_by,
            "trigger_source": trigger_source,
            "symbols_processed": 0,
            "records_created": 0,
            "records_updated": 0,
            "records_failed": 1,
            "agent_run_recorded": agent_run_recorded,
            "error": str(exc),
        }
