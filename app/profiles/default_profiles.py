from app.profiles.profile_models import StrategyProfile, StrategyProfileType


def get_balanced_research_default() -> StrategyProfile:
    return StrategyProfile(
        profile_name="Balanced Research Default",
        profile_type=StrategyProfileType.BALANCED,
        profile_version="balanced_research_default_1.0",
        stock_thesis_horizon_min_trading_days=10,
        stock_thesis_horizon_max_trading_days=25,
        option_dte_min=45,
        option_dte_max=90,
        premium_min_usd=500,
        premium_max_usd=1000,
        minimum_risk_reward=2.0,
        reject_if_target_below_breakeven=True,
        minimum_target_breakeven_margin_percent=3,
        iv_warning_threshold=70,
        iv_reject_threshold=85,
        earnings_risk_window_days=7,
        market_data_refresh_minutes=30,
        option_chain_refresh_minutes=60,
        news_refresh_minutes=60,
        watchlist_news_refresh_minutes=30,
        filing_refresh_minutes=60,
        earnings_calendar_refresh="daily",
        iv_risk_refresh_minutes=60,
        recommendation_job="after_market_close_plus_manual",
        outcome_tracking_job="after_market_close",
        learning_report="weekly",
        hard_filters_can_be_bypassed=False,
    )


def get_conservative_research() -> StrategyProfile:
    return StrategyProfile(
        profile_name="Conservative Research",
        profile_type=StrategyProfileType.CONSERVATIVE,
        profile_version="conservative_research_1.0",
        stock_thesis_horizon_min_trading_days=10,
        stock_thesis_horizon_max_trading_days=25,
        option_dte_min=60,
        option_dte_max=120,
        premium_min_usd=300,
        premium_max_usd=800,
        minimum_risk_reward=2.5,
        reject_if_target_below_breakeven=True,
        minimum_target_breakeven_margin_percent=5,
        iv_warning_threshold=60,
        iv_reject_threshold=80,
        earnings_risk_window_days=10,
        market_data_refresh_minutes=30,
        option_chain_refresh_minutes=60,
        news_refresh_minutes=60,
        watchlist_news_refresh_minutes=30,
        filing_refresh_minutes=60,
        earnings_calendar_refresh="daily",
        iv_risk_refresh_minutes=60,
        recommendation_job="after_market_close_plus_manual",
        outcome_tracking_job="after_market_close",
        learning_report="weekly",
        hard_filters_can_be_bypassed=False,
    )


def get_aggressive_research() -> StrategyProfile:
    return StrategyProfile(
        profile_name="Aggressive Research",
        profile_type=StrategyProfileType.AGGRESSIVE,
        profile_version="aggressive_research_1.0",
        stock_thesis_horizon_min_trading_days=5,
        stock_thesis_horizon_max_trading_days=25,
        option_dte_min=30,
        option_dte_max=90,
        premium_min_usd=300,
        premium_max_usd=1500,
        minimum_risk_reward=1.7,
        reject_if_target_below_breakeven=True,
        minimum_target_breakeven_margin_percent=2,
        iv_warning_threshold=75,
        iv_reject_threshold=90,
        earnings_risk_window_days=5,
        market_data_refresh_minutes=30,
        option_chain_refresh_minutes=60,
        news_refresh_minutes=60,
        watchlist_news_refresh_minutes=30,
        filing_refresh_minutes=60,
        earnings_calendar_refresh="daily",
        iv_risk_refresh_minutes=60,
        recommendation_job="after_market_close_plus_manual",
        outcome_tracking_job="after_market_close",
        learning_report="weekly",
        hard_filters_can_be_bypassed=False,
    )


def get_custom_profile_template() -> StrategyProfile:
    base_profile = get_balanced_research_default()

    return base_profile.model_copy(
        update={
            "profile_name": "Custom",
            "profile_type": StrategyProfileType.CUSTOM,
            "profile_version": "custom_1.0",
            "hard_filters_can_be_bypassed": False,
        }
    )


def get_default_profiles() -> list[StrategyProfile]:
    return [
        get_balanced_research_default(),
        get_conservative_research(),
        get_aggressive_research(),
        get_custom_profile_template(),
    ]