"""Phase 8 placeholder refresh job.

This job intentionally records a successful placeholder run without fetching
real option-chain data. Real option collection is deferred until a provider
with usable API access is selected.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.agent.agent_run_recorder import record_agent_run
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
            "Automatic option-chain collection is not enabled; no option "
            "snapshots were fetched or stored. Paste option contract data "
            "manually to evaluate the option side."
        ),
        "result": details,
    }


__all__ = ["record_agent_run", "run_option_chain_refresh_job"]