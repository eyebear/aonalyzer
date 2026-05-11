from dataclasses import dataclass

from app.core.config import get_settings


@dataclass(frozen=True)
class ScanSchedule:
    market_data_refresh_minutes: int
    option_chain_refresh_minutes: int
    news_refresh_minutes: int
    watchlist_news_refresh_minutes: int
    filing_refresh_minutes: int
    iv_risk_refresh_minutes: int
    earnings_calendar_refresh: str
    recommendations_schedule: str
    outcome_tracking_schedule: str
    learning_report_schedule: str
    automatic_scans_enabled: bool = True


class ScanScheduleManager:
    def __init__(self) -> None:
        self._automatic_scans_enabled = True

    def get_default_schedule(self) -> ScanSchedule:
        settings = get_settings()

        return ScanSchedule(
            market_data_refresh_minutes=settings.market_data_refresh_minutes,
            option_chain_refresh_minutes=settings.option_chain_refresh_minutes,
            news_refresh_minutes=settings.news_refresh_minutes,
            watchlist_news_refresh_minutes=settings.watchlist_news_refresh_minutes,
            filing_refresh_minutes=settings.filing_refresh_minutes,
            iv_risk_refresh_minutes=settings.iv_risk_refresh_minutes,
            earnings_calendar_refresh="daily",
            recommendations_schedule="after_market_close_plus_manual",
            outcome_tracking_schedule="after_market_close",
            learning_report_schedule="weekly",
            automatic_scans_enabled=self._automatic_scans_enabled,
        )

    def pause_automatic_scans(self) -> ScanSchedule:
        self._automatic_scans_enabled = False
        return self.get_default_schedule()

    def resume_automatic_scans(self) -> ScanSchedule:
        self._automatic_scans_enabled = True
        return self.get_default_schedule()

    def automatic_scans_enabled(self) -> bool:
        return self._automatic_scans_enabled


scan_schedule_manager = ScanScheduleManager()