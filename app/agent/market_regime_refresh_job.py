from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.agent.agent_run_recorder import record_agent_run
from app.common.service_utils import ensure_tables
from app.market_regime.market_regime_service import MarketRegimeService


def run_market_regime_refresh_job(
    db: Session,
    fetch_missing: bool = False,
    triggered_by: str = "USER",
    trigger_source: str = "API",
    market_regime_service: MarketRegimeService | None = None,
) -> dict[str, Any]:
    ensure_tables(db)

    service = market_regime_service or MarketRegimeService()

    try:
        result = service.refresh_market_regime(db=db, fetch_missing=fetch_missing)

        produced = result.records_created > 0 or result.records_updated > 0

        if result.records_failed > 0 and produced:
            status = "PARTIAL_SUCCESS"
        elif result.records_failed > 0 and not produced:
            status = "FAILED"
        else:
            status = "SUCCESS"

        details = result.to_dict()

        error_message = None
        if status == "FAILED":
            error_message = (
                "; ".join(f"{k}: {v}" for k, v in result.failed_reasons.items())
                or "Market regime refresh produced no snapshot."
            )

        agent_run_recorded = record_agent_run(
            db=db,
            job_name="market_regime_refresh",
            job_type="MARKET_REGIME",
            status=status,
            triggered_by=triggered_by,
            trigger_source=trigger_source,
            symbols_processed=len(result.fetched_symbols),
            records_created=result.records_created,
            records_updated=result.records_updated,
            records_failed=result.records_failed,
            error_message=error_message,
            details=details,
        )

        return {
            "status": status,
            "job_name": "market_regime_refresh",
            "job_type": "MARKET_REGIME",
            "triggered_by": triggered_by,
            "trigger_source": trigger_source,
            "symbols_processed": len(result.fetched_symbols),
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
            job_name="market_regime_refresh",
            job_type="MARKET_REGIME",
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
            "job_name": "market_regime_refresh",
            "job_type": "MARKET_REGIME",
            "triggered_by": triggered_by,
            "trigger_source": trigger_source,
            "symbols_processed": 0,
            "records_created": 0,
            "records_updated": 0,
            "records_failed": 1,
            "agent_run_recorded": agent_run_recorded,
            "error": str(exc),
        }


__all__ = ["run_market_regime_refresh_job"]
