from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.agent.market_data_refresh_job import record_agent_run
from app.database.base import Base
from app.macro.macro_data_service import MacroDataService


def run_macro_refresh_job(
    db: Session,
    triggered_by: str = "USER",
    trigger_source: str = "API",
    macro_service: MacroDataService | None = None,
) -> dict[str, Any]:
    Base.metadata.create_all(bind=db.get_bind())

    service = macro_service or MacroDataService()

    try:
        result = service.refresh_macro_events(db=db)

        if result.records_created > 0:
            status = "SUCCESS"
        elif result.failed_sources and result.items_fetched == 0:
            status = "FAILED"
        else:
            status = "SUCCESS"

        details = result.to_dict()

        agent_run_recorded = record_agent_run(
            db=db,
            job_name="macro_refresh",
            job_type="MACRO",
            status=status,
            triggered_by=triggered_by,
            trigger_source=trigger_source,
            symbols_processed=0,
            records_created=result.records_created,
            records_updated=result.records_updated,
            records_failed=result.records_failed,
            error_message=None if status != "FAILED" else "Macro refresh failed.",
            details=details,
        )

        return {
            "status": status,
            "job_name": "macro_refresh",
            "job_type": "MACRO",
            "triggered_by": triggered_by,
            "trigger_source": trigger_source,
            "symbols_processed": 0,
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
            job_name="macro_refresh",
            job_type="MACRO",
            status="FAILED",
            triggered_by=triggered_by,
            trigger_source=trigger_source,
            symbols_processed=0,
            records_created=0,
            records_updated=0,
            records_failed=1,
            error_message=str(exc),
            details={"error": str(exc)},
        )

        return {
            "status": "FAILED",
            "job_name": "macro_refresh",
            "job_type": "MACRO",
            "triggered_by": triggered_by,
            "trigger_source": trigger_source,
            "symbols_processed": 0,
            "records_created": 0,
            "records_updated": 0,
            "records_failed": 1,
            "agent_run_recorded": agent_run_recorded,
            "error": str(exc),
        }
