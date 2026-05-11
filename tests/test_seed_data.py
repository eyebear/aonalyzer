from app.database.seed_data import (
    INITIAL_SCAN_SCHEDULE_SETTINGS,
    INITIAL_TICKERS,
    INITIAL_VERSION_REGISTRY,
    get_initial_default_strategy_profile_record,
    get_initial_strategy_profile_version_record,
)


def test_initial_tickers_include_us_canadian_and_etf_symbols() -> None:
    symbols = {ticker["symbol"] for ticker in INITIAL_TICKERS}

    assert "AAPL" in symbols
    assert "MSFT" in symbols
    assert "NVDA" in symbols
    assert "AMD" in symbols
    assert "SPY" in symbols
    assert "QQQ" in symbols
    assert "SHOP.TO" in symbols
    assert "RY.TO" in symbols


def test_initial_scan_schedule_settings_include_required_jobs() -> None:
    setting_names = {setting["setting_name"] for setting in INITIAL_SCAN_SCHEDULE_SETTINGS}

    assert "market_data_refresh" in setting_names
    assert "option_chain_refresh" in setting_names
    assert "news_refresh" in setting_names
    assert "watchlist_news_refresh" in setting_names
    assert "filing_refresh" in setting_names
    assert "earnings_calendar_refresh" in setting_names
    assert "iv_risk_refresh" in setting_names


def test_initial_default_strategy_profile_record_loads() -> None:
    record = get_initial_default_strategy_profile_record()

    assert record["profile_name"] == "Balanced Research Default"
    assert record["profile_type"] == "BALANCED"
    assert record["profile_version"] == "balanced_research_default_1.0"
    assert record["is_default"] is True
    assert record["is_active"] is True
    assert record["profile_json"]["option_dte_min"] == 45
    assert record["profile_json"]["option_dte_max"] == 90
    assert record["profile_json"]["hard_filters_can_be_bypassed"] is False


def test_initial_strategy_profile_version_record_loads() -> None:
    record = get_initial_strategy_profile_version_record()

    assert record["profile_name"] == "Balanced Research Default"
    assert record["profile_version"] == "balanced_research_default_1.0"
    assert record["profile_type"] == "BALANCED"
    assert record["is_active"] is True


def test_initial_version_registry_contains_required_versions() -> None:
    version_keys = {version["version_key"] for version in INITIAL_VERSION_REGISTRY}

    assert "rule_version" in version_keys
    assert "strategy_profile_version" in version_keys
    assert "data_schema_version" in version_keys
    assert "decision_engine_version" in version_keys
    assert "action_suggestion_version" in version_keys