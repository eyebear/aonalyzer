from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.agent.market_data_refresh_job import record_agent_run
from app.common.service_utils import ensure_tables
from app.iv_history.iv_history_service import IvHistoryService
from app.iv_history.iv_risk_service import IvRiskService


def run_iv_risk_refresh_job(
    db: Session,
    symbols: list[str] | None = None,
    triggered_by: str = "USER",
    trigger_source: str = "API",
    iv_history_service: IvHistoryService | None = None,
    iv_risk_service: IvRiskService | None = None,
    skip_history_fetch: bool = False,
) -> dict[str, Any]:
    ensure_tables(db)

    history_service = iv_history_service or IvHistoryService()
    risk_service = iv_risk_service or IvRiskService()

    try:
        history_result_dict: dict[str, Any] | None = None
        if not skip_history_fetch and symbols:
            history_result = history_service.refresh_ticker_iv_history(
                db=db, symbols=symbols
            )
            history_result_dict = history_result.to_dict()

        risk_result_dict: dict[str, Any] | None = None
        if symbols:
            risk_result = risk_service.refresh_iv_risk(db=db, symbols=symbols)
            risk_result_dict = risk_result.to_dict()
            records_created = risk_result.records_created
            records_updated = risk_result.records_updated
            records_failed = risk_result.records_failed
            symbols_processed = len(risk_result.successful_symbols)
        else:
            records_created = 0
            records_updated = 0
            records_failed = 0
            symbols_processed = 0

        status = "SUCCESS" if records_failed == 0 else "PARTIAL_SUCCESS"
        if records_failed > 0 and symbols_processed == 0:
            status = "FAILED"

        details = {
            "history": history_result_dict,
            "risk": risk_result_dict,
        }

        agent_run_recorded = record_agent_run(
            db=db,
            job_name="iv_risk_refresh",
            job_type="IV_RISK",
            status=status,
            triggered_by=triggered_by,
            trigger_source=trigger_source,
            symbols_processed=symbols_processed,
            records_created=records_created,
            records_updated=records_updated,
            records_failed=records_failed,
            error_message=None if status != "FAILED" else "IV risk refresh failed.",
            details=details,
        )

        return {
            "status": status,
            "job_name": "iv_risk_refresh",
            "job_type": "IV_RISK",
            "triggered_by": triggered_by,
            "trigger_source": trigger_source,
            "symbols_processed": symbols_processed,
            "records_created": records_created,
            "records_updated": records_updated,
            "records_failed": records_failed,
            "agent_run_recorded": agent_run_recorded,
            "result": details,
        }

    except Exception as exc:
        db.rollback()

        agent_run_recorded = record_agent_run(
            db=db,
            job_name="iv_risk_refresh",
            job_type="IV_RISK",
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
            "job_name": "iv_risk_refresh",
            "job_type": "IV_RISK",
            "triggered_by": triggered_by,
            "trigger_source": trigger_source,
            "symbols_processed": 0,
            "records_created": 0,
            "records_updated": 0,
            "records_failed": 1,
            "agent_run_recorded": agent_run_recorded,
            "error": str(exc),
        }
