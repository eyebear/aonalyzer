from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.agent.market_data_refresh_job import record_agent_run
from app.database.base import Base
from app.news.news_service import NewsService


def run_news_refresh_job(
    db: Session,
    symbols: list[str] | None = None,
    triggered_by: str = "USER",
    trigger_source: str = "API",
    news_service: NewsService | None = None,
) -> dict[str, Any]:
    Base.metadata.create_all(bind=db.get_bind())

    service = news_service or NewsService()

    try:
        result = service.refresh_ticker_news(
            db=db,
            symbols=symbols,
        )

        if result.records_created > 0 and result.failed_symbols:
            status = "PARTIAL_SUCCESS"
        elif result.records_created > 0:
            status = "SUCCESS"
        elif result.successful_symbols and not result.failed_symbols:
            status = "SUCCESS"
        elif result.failed_symbols and not result.successful_symbols:
            status = "FAILED"
        else:
            status = "SUCCESS"

        details = result.to_dict()

        agent_run_recorded = record_agent_run(
            db=db,
            job_name="news_refresh",
            job_type="NEWS",
            status=status,
            triggered_by=triggered_by,
            trigger_source=trigger_source,
            symbols_processed=len(result.successful_symbols),
            records_created=result.records_created,
            records_updated=result.records_updated,
            records_failed=len(result.failed_symbols),
            error_message=None if status != "FAILED" else "News refresh failed for all symbols.",
            details=details,
        )

        return {
            "status": status,
            "job_name": "news_refresh",
            "job_type": "NEWS",
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
            job_name="news_refresh",
            job_type="NEWS",
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
            "job_name": "news_refresh",
            "job_type": "NEWS",
            "triggered_by": triggered_by,
            "trigger_source": trigger_source,
            "symbols_processed": 0,
            "records_created": 0,
            "records_updated": 0,
            "records_failed": 1,
            "agent_run_recorded": agent_run_recorded,
            "error": str(exc),
        }
