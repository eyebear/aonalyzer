from __future__ import annotations

"""
Phase 8 placeholder refresh job.

This job intentionally records a successful placeholder run without fetching
real option-chain data. Real option collection is deferred until a provider
with usable API access is selected.
"""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.options.option_chain_service import OptionChainService


def run_option_chain_refresh_job(
    db: Session,
    symbols: list[str] | None = None,
    triggered_by: str = "USER",
    trigger_source: str = "API",
    max_expirations: int = 4,
) -> dict[str, Any]:
    service = OptionChainService()

    result = service.refresh_option_chains(
        db=db,
        symbols=symbols,
        max_expirations=max_expirations,
    )

    details = result.to_dict()

    agent_run_recorded = record_agent_run(
        db=db,
        job_name="option_chain_refresh",
        job_type="OPTIONS",
        status="SUCCESS",
        triggered_by=triggered_by,
        trigger_source=trigger_source,
        symbols_processed=len(result.requested_symbols),
        records_created=0,
        records_updated=0,
        records_failed=0,
        error_message=None,
        details=details,
    )

    return {
        "status": "SUCCESS",
        "job_name": "option_chain_refresh",
        "job_type": "OPTIONS",
        "triggered_by": triggered_by,
        "trigger_source": trigger_source,
        "symbols_processed": len(result.requested_symbols),
        "records_created": 0,
        "records_updated": 0,
        "records_failed": 0,
        "agent_run_recorded": agent_run_recorded,
        "placeholder": True,
        "message": (
            "Phase 8 option-chain collection is currently a placeholder. "
            "No real option snapshots were fetched or stored."
        ),
        "result": details,
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
        "message": details.get("message"),
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