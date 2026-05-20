from dataclasses import dataclass


@dataclass(frozen=True)
class RegisteredJob:
    job_name: str
    job_type: str
    description: str
    default_trigger: str


class ScheduledJobRegistry:
    def __init__(self) -> None:
        self._jobs = {
            "refresh_all": RegisteredJob(
                job_name="refresh_all",
                job_type="MANUAL_REFRESH",
                description="Run all available refresh placeholders.",
                default_trigger="manual",
            ),
            "market_data_refresh": RegisteredJob(
                job_name="market_data_refresh",
                job_type="MARKET_DATA",
                description="Refresh market data placeholder.",
                default_trigger="manual_or_schedule",
            ),
            "option_chain_refresh": RegisteredJob(
                job_name="option_chain_refresh",
                job_type="OPTIONS",
                description="Refresh option chain placeholder.",
                default_trigger="manual_or_schedule",
            ),
            "news_refresh": RegisteredJob(
                job_name="news_refresh",
                job_type="NEWS",
                description="Refresh news placeholder.",
                default_trigger="manual_or_schedule",
            ),
            "filing_refresh": RegisteredJob(
                job_name="filing_refresh",
                job_type="FILINGS",
                description="Refresh filings placeholder.",
                default_trigger="manual_or_schedule",
            ),
            "earnings_refresh": RegisteredJob(
                job_name="earnings_refresh",
                job_type="EARNINGS",
                description="Refresh earnings calendar placeholder.",
                default_trigger="manual_or_schedule",
            ),
            "iv_risk_refresh": RegisteredJob(
                job_name="iv_risk_refresh",
                job_type="IV_RISK",
                description="Refresh IV risk placeholder.",
                default_trigger="manual_or_schedule",
            ),
            "recommendation_run": RegisteredJob(
                job_name="recommendation_run",
                job_type="RECOMMENDATIONS",
                description="Run recommendation placeholder.",
                default_trigger="manual_or_schedule",
            ),
            "test_refresh": RegisteredJob(
                job_name="test_refresh",
                job_type="TEST",
                description="Test manual refresh logging.",
                default_trigger="manual",
            ),
            "macro_refresh": RegisteredJob(
                job_name="macro_refresh",
                job_type="MACRO",
                description="Refresh macro economic events.",
                default_trigger="manual_or_schedule",
            ),
            "company_ir_refresh": RegisteredJob(
                job_name="company_ir_refresh",
                job_type="COMPANY_IR",
                description="Refresh company investor relations events.",
                default_trigger="manual_or_schedule",
            ),
            "technical_refresh": RegisteredJob(
                job_name="technical_refresh",
                job_type="TECHNICAL",
                description=(
                    "Compute technical-analysis snapshots from stored daily prices."
                ),
                default_trigger="manual_or_schedule",
            ),
            "stock_setup_refresh": RegisteredJob(
                job_name="stock_setup_refresh",
                job_type="STOCK_SETUP",
                description=(
                    "Compute support/resistance, entry, target, stop, and "
                    "risk/reward setup math from stored prices and the latest "
                    "technical snapshot."
                ),
                default_trigger="manual_or_schedule",
            ),
            "market_regime_refresh": RegisteredJob(
                job_name="market_regime_refresh",
                job_type="MARKET_REGIME",
                description=(
                    "Compute broad market regime (SPY/QQQ/IWM trend, VIX state, "
                    "10Y-yield pressure) and sector relative strength from stored "
                    "daily prices."
                ),
                default_trigger="manual_or_schedule",
            ),
            "setup_detection_refresh": RegisteredJob(
                job_name="setup_detection_refresh",
                job_type="SETUP_DETECTION",
                description=(
                    "Detect stock setup type (pullback/breakout-retest/sector-"
                    "strength long, breakdown short, oversold-bounce watch, or "
                    "no-trade) with a quality score from technical, setup, and "
                    "regime context."
                ),
                default_trigger="manual_or_schedule",
            ),
        }

    def list_jobs(self) -> list[RegisteredJob]:
        return list(self._jobs.values())

    def get_job(self, job_name: str) -> RegisteredJob:
        if job_name not in self._jobs:
            raise KeyError(f"Unknown registered job: {job_name}")

        return self._jobs[job_name]


scheduled_job_registry = ScheduledJobRegistry()