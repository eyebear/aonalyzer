from app.database.base import Base
from app.database.models import (
    AgentRun,
    DailyPrice,
    DefaultStrategyProfile,
    Event,
    IntradayPrice,
    ScanScheduleSetting,
    StrategyProfileVersion,
    Ticker,
    VersionRegistry,
    Watchlist,
)


def test_core_database_tables_are_registered() -> None:
    table_names = set(Base.metadata.tables.keys())

    assert "tickers" in table_names
    assert "watchlists" in table_names
    assert "daily_prices" in table_names
    assert "intraday_prices" in table_names
    assert "events" in table_names
    assert "agent_runs" in table_names
    assert "scan_schedule_settings" in table_names
    assert "default_strategy_profiles" in table_names
    assert "version_registry" in table_names
    assert "strategy_profile_versions" in table_names


def test_core_model_table_names() -> None:
    assert Ticker.__tablename__ == "tickers"
    assert Watchlist.__tablename__ == "watchlists"
    assert DailyPrice.__tablename__ == "daily_prices"
    assert IntradayPrice.__tablename__ == "intraday_prices"
    assert Event.__tablename__ == "events"
    assert AgentRun.__tablename__ == "agent_runs"
    assert ScanScheduleSetting.__tablename__ == "scan_schedule_settings"
    assert DefaultStrategyProfile.__tablename__ == "default_strategy_profiles"
    assert VersionRegistry.__tablename__ == "version_registry"
    assert StrategyProfileVersion.__tablename__ == "strategy_profile_versions"


def test_tickers_table_has_expected_columns() -> None:
    columns = set(Ticker.__table__.columns.keys())

    assert "id" in columns
    assert "symbol" in columns
    assert "name" in columns
    assert "market" in columns
    assert "asset_type" in columns
    assert "currency" in columns
    assert "exchange" in columns
    assert "is_active" in columns


def test_agent_runs_tracks_manual_and_scheduled_jobs() -> None:
    columns = set(AgentRun.__table__.columns.keys())

    assert "job_name" in columns
    assert "job_type" in columns
    assert "status" in columns
    assert "triggered_by" in columns
    assert "trigger_source" in columns
    assert "records_created" in columns
    assert "records_updated" in columns
    assert "records_failed" in columns


def test_strategy_profile_tables_have_version_fields() -> None:
    default_profile_columns = set(DefaultStrategyProfile.__table__.columns.keys())
    version_columns = set(StrategyProfileVersion.__table__.columns.keys())

    assert "profile_version" in default_profile_columns
    assert "profile_json" in default_profile_columns
    assert "profile_version" in version_columns
    assert "profile_json" in version_columns