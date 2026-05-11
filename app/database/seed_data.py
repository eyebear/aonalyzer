from app.profiles.default_profiles import get_balanced_research_default

INITIAL_TICKERS = [
    {
        "symbol": "AAPL",
        "name": "Apple Inc.",
        "market": "US",
        "asset_type": "STOCK",
        "currency": "USD",
        "exchange": "NASDAQ",
    },
    {
        "symbol": "MSFT",
        "name": "Microsoft Corporation",
        "market": "US",
        "asset_type": "STOCK",
        "currency": "USD",
        "exchange": "NASDAQ",
    },
    {
        "symbol": "NVDA",
        "name": "NVIDIA Corporation",
        "market": "US",
        "asset_type": "STOCK",
        "currency": "USD",
        "exchange": "NASDAQ",
    },
    {
        "symbol": "AMD",
        "name": "Advanced Micro Devices, Inc.",
        "market": "US",
        "asset_type": "STOCK",
        "currency": "USD",
        "exchange": "NASDAQ",
    },
    {
        "symbol": "TSLA",
        "name": "Tesla, Inc.",
        "market": "US",
        "asset_type": "STOCK",
        "currency": "USD",
        "exchange": "NASDAQ",
    },
    {
        "symbol": "SPY",
        "name": "SPDR S&P 500 ETF Trust",
        "market": "US",
        "asset_type": "ETF",
        "currency": "USD",
        "exchange": "NYSEARCA",
    },
    {
        "symbol": "QQQ",
        "name": "Invesco QQQ Trust",
        "market": "US",
        "asset_type": "ETF",
        "currency": "USD",
        "exchange": "NASDAQ",
    },
    {
        "symbol": "IWM",
        "name": "iShares Russell 2000 ETF",
        "market": "US",
        "asset_type": "ETF",
        "currency": "USD",
        "exchange": "NYSEARCA",
    },
    {
        "symbol": "SHOP.TO",
        "name": "Shopify Inc.",
        "market": "Canada",
        "asset_type": "STOCK",
        "currency": "CAD",
        "exchange": "TSX",
    },
    {
        "symbol": "RY.TO",
        "name": "Royal Bank of Canada",
        "market": "Canada",
        "asset_type": "STOCK",
        "currency": "CAD",
        "exchange": "TSX",
    },
    {
        "symbol": "TD.TO",
        "name": "The Toronto-Dominion Bank",
        "market": "Canada",
        "asset_type": "STOCK",
        "currency": "CAD",
        "exchange": "TSX",
    },
    {
        "symbol": "ENB.TO",
        "name": "Enbridge Inc.",
        "market": "Canada",
        "asset_type": "STOCK",
        "currency": "CAD",
        "exchange": "TSX",
    },
]


INITIAL_SCAN_SCHEDULE_SETTINGS = [
    {
        "setting_name": "market_data_refresh",
        "refresh_minutes": 30,
        "schedule_value": "market_hours",
        "is_enabled": True,
    },
    {
        "setting_name": "option_chain_refresh",
        "refresh_minutes": 60,
        "schedule_value": "market_hours",
        "is_enabled": True,
    },
    {
        "setting_name": "news_refresh",
        "refresh_minutes": 60,
        "schedule_value": "always",
        "is_enabled": True,
    },
    {
        "setting_name": "watchlist_news_refresh",
        "refresh_minutes": 30,
        "schedule_value": "always",
        "is_enabled": True,
    },
    {
        "setting_name": "filing_refresh",
        "refresh_minutes": 60,
        "schedule_value": "always",
        "is_enabled": True,
    },
    {
        "setting_name": "earnings_calendar_refresh",
        "refresh_minutes": None,
        "schedule_value": "daily",
        "is_enabled": True,
    },
    {
        "setting_name": "iv_risk_refresh",
        "refresh_minutes": 60,
        "schedule_value": "market_hours",
        "is_enabled": True,
    },
]


INITIAL_VERSION_REGISTRY = [
    {
        "version_key": "rule_version",
        "version_value": "ruleset_2026_05_v1",
        "version_type": "RULE",
        "description": "Initial rule version for Ao Ao Analyzer.",
        "is_active": True,
    },
    {
        "version_key": "strategy_profile_version",
        "version_value": "balanced_research_default_1.0",
        "version_type": "STRATEGY_PROFILE",
        "description": "Initial Balanced Research Default profile version.",
        "is_active": True,
    },
    {
        "version_key": "data_schema_version",
        "version_value": "aoao_schema_0.1",
        "version_type": "DATA_SCHEMA",
        "description": "Initial database schema version.",
        "is_active": True,
    },
    {
        "version_key": "decision_engine_version",
        "version_value": "decision_engine_0.1",
        "version_type": "DECISION_ENGINE",
        "description": "Initial decision engine placeholder version.",
        "is_active": True,
    },
    {
        "version_key": "action_suggestion_version",
        "version_value": "action_suggestion_0.1",
        "version_type": "ACTION_SUGGESTION",
        "description": "Initial action suggestion placeholder version.",
        "is_active": True,
    },
]


def get_initial_default_strategy_profile_record() -> dict:
    profile = get_balanced_research_default()

    return {
        "profile_name": profile.profile_name,
        "profile_type": profile.profile_type.value,
        "profile_version": profile.profile_version,
        "profile_json": profile.model_dump(mode="json"),
        "is_default": True,
        "is_active": True,
    }


def get_initial_strategy_profile_version_record() -> dict:
    profile = get_balanced_research_default()

    return {
        "profile_name": profile.profile_name,
        "profile_type": profile.profile_type.value,
        "profile_version": profile.profile_version,
        "profile_json": profile.model_dump(mode="json"),
        "is_active": True,
    }