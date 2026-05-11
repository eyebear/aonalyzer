from app.agent.scan_schedule_manager import scan_schedule_manager
from app.agent.scheduled_job_registry import scheduled_job_registry
from app.agent.scheduler import agent_scheduler


def test_default_scan_schedule_loads() -> None:
    schedule = scan_schedule_manager.get_default_schedule()

    assert schedule.market_data_refresh_minutes == 30
    assert schedule.option_chain_refresh_minutes == 60
    assert schedule.news_refresh_minutes == 60
    assert schedule.watchlist_news_refresh_minutes == 30
    assert schedule.filing_refresh_minutes == 60
    assert schedule.iv_risk_refresh_minutes == 60
    assert schedule.automatic_scans_enabled is True


def test_pause_and_resume_automatic_scans() -> None:
    paused_schedule = scan_schedule_manager.pause_automatic_scans()

    assert paused_schedule.automatic_scans_enabled is False
    assert scan_schedule_manager.automatic_scans_enabled() is False

    resumed_schedule = scan_schedule_manager.resume_automatic_scans()

    assert resumed_schedule.automatic_scans_enabled is True
    assert scan_schedule_manager.automatic_scans_enabled() is True


def test_scheduled_job_registry_contains_required_jobs() -> None:
    job_names = {job.job_name for job in scheduled_job_registry.list_jobs()}

    assert "refresh_all" in job_names
    assert "market_data_refresh" in job_names
    assert "option_chain_refresh" in job_names
    assert "news_refresh" in job_names
    assert "filing_refresh" in job_names
    assert "earnings_refresh" in job_names
    assert "iv_risk_refresh" in job_names
    assert "recommendation_run" in job_names
    assert "test_refresh" in job_names


def test_agent_scheduler_lists_registered_jobs() -> None:
    jobs = agent_scheduler.list_registered_jobs()
    job_names = {job["job_name"] for job in jobs}

    assert "refresh_all" in job_names
    assert "test_refresh" in job_names