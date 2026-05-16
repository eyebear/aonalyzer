from sqlalchemy.orm import Session

from app.agent.job_run_logger import job_run_logger
from app.agent.scheduled_job_registry import scheduled_job_registry
from app.database.models import AgentRun


class ManualRefreshController:
    def run_test_refresh(self, session: Session) -> AgentRun:
        return self._run_placeholder_job(
            session=session,
            job_name="test_refresh",
            triggered_by="USER",
            trigger_source="API",
            records_created=1,
        )

    def refresh_all(self, session: Session) -> AgentRun:
        return self._run_placeholder_job(
            session=session,
            job_name="refresh_all",
            triggered_by="USER",
            trigger_source="API",
            records_created=1,
        )

    def refresh_market_data(self, session: Session) -> AgentRun:
        return self._run_placeholder_job(
            session=session,
            job_name="market_data_refresh",
            triggered_by="USER",
            trigger_source="API",
            records_created=0,
        )

    def refresh_options(self, session: Session) -> AgentRun:
        return self._run_placeholder_job(
            session=session,
            job_name="option_chain_refresh",
            triggered_by="USER",
            trigger_source="API",
            records_created=0,
        )

    def refresh_news(self, session: Session) -> AgentRun:
        return self._run_placeholder_job(
            session=session,
            job_name="news_refresh",
            triggered_by="USER",
            trigger_source="API",
            records_created=0,
        )

    def refresh_filings(self, session: Session) -> AgentRun:
        return self._run_placeholder_job(
            session=session,
            job_name="filing_refresh",
            triggered_by="USER",
            trigger_source="API",
            records_created=0,
        )

    def refresh_earnings(self, session: Session) -> AgentRun:
        return self._run_placeholder_job(
            session=session,
            job_name="earnings_refresh",
            triggered_by="USER",
            trigger_source="API",
            records_created=0,
        )

    def refresh_macro(self, session: Session) -> AgentRun:
        return self._run_placeholder_job(
            session=session,
            job_name="macro_refresh",
            triggered_by="USER",
            trigger_source="API",
            records_created=0,
        )

    def refresh_technical(self, session: Session) -> AgentRun:
        return self._run_placeholder_job(
            session=session,
            job_name="technical_refresh",
            triggered_by="USER",
            trigger_source="API",
            records_created=0,
        )

    def refresh_stock_setup(self, session: Session) -> AgentRun:
        return self._run_placeholder_job(
            session=session,
            job_name="stock_setup_refresh",
            triggered_by="USER",
            trigger_source="API",
            records_created=0,
        )

    def refresh_iv_risk(self, session: Session) -> AgentRun:
        return self._run_placeholder_job(
            session=session,
            job_name="iv_risk_refresh",
            triggered_by="USER",
            trigger_source="API",
            records_created=0,
        )

    def run_recommendations(self, session: Session) -> AgentRun:
        return self._run_placeholder_job(
            session=session,
            job_name="recommendation_run",
            triggered_by="USER",
            trigger_source="API",
            records_created=0,
        )

    def refresh_ticker_market_data(self, session: Session, symbol: str) -> AgentRun:
        return self._run_placeholder_job(
            session=session,
            job_name=f"ticker_market_data_refresh:{symbol.upper()}",
            job_type="TICKER_MARKET_DATA",
            triggered_by="USER",
            trigger_source="API",
            symbols_processed=1,
        )

    def refresh_ticker_options(self, session: Session, symbol: str) -> AgentRun:
        return self._run_placeholder_job(
            session=session,
            job_name=f"ticker_option_refresh:{symbol.upper()}",
            job_type="TICKER_OPTIONS",
            triggered_by="USER",
            trigger_source="API",
            symbols_processed=1,
        )

    def refresh_ticker_news(self, session: Session, symbol: str) -> AgentRun:
        return self._run_placeholder_job(
            session=session,
            job_name=f"ticker_news_refresh:{symbol.upper()}",
            job_type="TICKER_NEWS",
            triggered_by="USER",
            trigger_source="API",
            symbols_processed=1,
        )

    def analyze_ticker(self, session: Session, symbol: str) -> AgentRun:
        return self._run_placeholder_job(
            session=session,
            job_name=f"ticker_analysis:{symbol.upper()}",
            job_type="TICKER_ANALYSIS",
            triggered_by="USER",
            trigger_source="API",
            symbols_processed=1,
        )

    def _run_placeholder_job(
        self,
        session: Session,
        job_name: str,
        triggered_by: str,
        trigger_source: str,
        records_created: int = 0,
        records_updated: int = 0,
        records_failed: int = 0,
        symbols_processed: int = 0,
        job_type: str | None = None,
    ) -> AgentRun:
        if job_type is None:
            registered_job = scheduled_job_registry.get_job(job_name)
            job_type = registered_job.job_type

        def job_function() -> dict:
            return {
                "symbols_processed": symbols_processed,
                "records_created": records_created,
                "records_updated": records_updated,
                "records_failed": records_failed,
            }

        return job_run_logger.run_logged_job(
            session=session,
            job_name=job_name,
            job_type=job_type,
            triggered_by=triggered_by,
            trigger_source=trigger_source,
            job_function=job_function,
        )


manual_refresh_controller = ManualRefreshController()