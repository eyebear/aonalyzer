from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.agent.market_data_refresh_job import record_agent_run
from app.database.base import Base
from app.earnings.earnings_calendar_service import EarningsCalendarService
from app.earnings.earnings_risk_service import EarningsRiskService


def run_earnings_calendar_refresh_job(
    db: Session,
    symbols: list[str] | None = None,
    triggered_by: str = "USER",
    trigger_source: str = "API",
    earnings_calendar_service: EarningsCalendarService | None = None,
    earnings_risk_service: EarningsRiskService | None = None,
    skip_risk_snapshot: bool = False,
) -> dict[str, Any]:
    Base.metadata.create_all(bind=db.get_bind())

    calendar_service = earnings_calendar_service or EarningsCalendarService()
    risk_service = earnings_risk_service or EarningsRiskService()

    try:
        calendar_result = calendar_service.refresh_ticker_earnings(
            db=db, symbols=symbols
        )

        risk_result_dict: dict[str, Any] | None = None
        if not skip_risk_snapshot and symbols:
            risk_result = risk_service.refresh_earnings_risk(
                db=db, symbols=symbols
            )
            risk_result_dict = risk_result.to_dict()

        # SUCCESS is the default when at least one symbol produced a clean
        # snapshot OR when no rows are fetched (empty source is not a failure).
        if calendar_result.records_failed > 0 and not calendar_result.successful_symbols:
            status = "FAILED"
        elif calendar_result.records_failed > 0:
            status = "PARTIAL_SUCCESS"
        else:
            status = "SUCCESS"

        details = {
            "calendar": calendar_result.to_dict(),
            "risk": risk_result_dict,
        }

        agent_run_recorded = record_agent_run(
            db=db,
            job_name="earnings_refresh",
            job_type="EARNINGS",
            status=status,
            triggered_by=triggered_by,
            trigger_source=trigger_source,
            symbols_processed=len(calendar_result.successful_symbols),
            records_created=calendar_result.records_created,
            records_updated=calendar_result.records_updated,
            records_failed=calendar_result.records_failed,
            error_message=None if status != "FAILED" else "Earnings refresh failed.",
            details=details,
        )

        return {
            "status": status,
            "job_name": "earnings_refresh",
            "job_type": "EARNINGS",
            "triggered_by": triggered_by,
            "trigger_source": trigger_source,
            "symbols_processed": len(calendar_result.successful_symbols),
            "records_created": calendar_result.records_created,
            "records_updated": calendar_result.records_updated,
            "records_failed": calendar_result.records_failed,
            "agent_run_recorded": agent_run_recorded,
            "result": details,
        }

    except Exception as exc:
        db.rollback()

        agent_run_recorded = record_agent_run(
            db=db,
            job_name="earnings_refresh",
            job_type="EARNINGS",
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
            "job_name": "earnings_refresh",
            "job_type": "EARNINGS",
            "triggered_by": triggered_by,
            "trigger_source": trigger_source,
            "symbols_processed": 0,
            "records_created": 0,
            "records_updated": 0,
            "records_failed": 1,
            "agent_run_recorded": agent_run_recorded,
            "error": str(exc),
        }
