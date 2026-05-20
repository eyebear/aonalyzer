"""Single source of truth for recording agent-run rows from refresh jobs.

Previously this function was duplicated verbatim in ``market_data_refresh_job``
and ``option_chain_refresh_job`` (with a subtle divergence in how the optional
``message`` column was populated). All refresh jobs now import this one
implementation.

The INSERT is column-introspection based: it only writes columns that actually
exist on the ``agent_runs`` table, so it tolerates schema variants and is a no-op
(returns ``False``) when the table is absent.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session


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

    table_columns = {column["name"] for column in inspector.get_columns("agent_runs")}

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
        # Unified ``message`` semantics: prefer an explicit error, otherwise fall
        # back to a caller-provided ``details["message"]`` (only used by schema
        # variants that define a ``message`` column; dropped otherwise).
        "message": error_message or details.get("message"),
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


__all__ = ["record_agent_run"]
