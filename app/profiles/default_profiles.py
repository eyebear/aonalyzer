BALANCED_RESEARCH_DEFAULT = {
    "profile_name": "Balanced Research Default",
    "profile_type": "BALANCED",
    "stock_thesis_horizon_min_trading_days": 10,
    "stock_thesis_horizon_max_trading_days": 25,
    "option_dte_min": 45,
    "option_dte_max": 90,
    "premium_min_usd": 500,
    "premium_max_usd": 1000,
    "minimum_risk_reward": 2.0,
    "reject_if_target_below_breakeven": True,
    "minimum_target_breakeven_margin_percent": 3,
    "iv_warning_threshold": 70,
    "iv_reject_threshold": 85,
    "earnings_risk_window_days": 7,
    "market_data_refresh_minutes": 30,
    "option_chain_refresh_minutes": 60,
    "news_refresh_minutes": 60,
    "watchlist_news_refresh_minutes": 30,
    "filing_refresh_minutes": 60,
    "earnings_calendar_refresh": "daily",
    "iv_risk_refresh_minutes": 60,
    "recommendation_job": "after_market_close_plus_manual",
    "outcome_tracking_job": "after_market_close",
    "learning_report": "weekly",
}


def get_balanced_research_default() -> dict:
    return BALANCED_RESEARCH_DEFAULT.copy()
