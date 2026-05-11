# Default Strategy Profile

## Profile Name

Balanced Research Default

## Purpose

Balanced Research Default is the first-use strategy profile for Ao Ao Analyzer.

It prevents the system from overwhelming the user with too many settings at the start.

It provides practical default values for stock thesis, option expression, risk filters, refresh schedule, and decision behavior.

## Profile Types

Ao Ao Analyzer supports these profile types:

- Balanced Research Default
- Conservative Research
- Aggressive Research
- Custom

## Core Balanced Research Default Values

stock_thesis_horizon_min_trading_days = 10

stock_thesis_horizon_max_trading_days = 25

option_dte_min = 45

option_dte_max = 90

premium_min_usd = 500

premium_max_usd = 1000

minimum_risk_reward = 2.0

reject_if_target_below_breakeven = true

minimum_target_breakeven_margin_percent = 3

iv_warning_threshold = 70

iv_reject_threshold = 85

earnings_risk_window_days = 7

market_data_refresh_minutes = 30

option_chain_refresh_minutes = 60

news_refresh_minutes = 60

watchlist_news_refresh_minutes = 30

filing_refresh_minutes = 60

earnings_calendar_refresh = daily

iv_risk_refresh_minutes = 60

recommendation_job = after_market_close_plus_manual

outcome_tracking_job = after_market_close

learning_report = weekly

## Aggressive Profile Boundary

Aggressive Research can be more permissive, but it must not bypass hard fails.

Aggressive Research must not bypass:

- missing option data
- missing IV data
- target below breakeven
- extremely bad liquidity
- extremely high IV with dangerous event risk
- insufficient price history
- dangerous earnings/IV conditions
- Do-Not-Touch controls

## User-Facing Settings Groups

Settings should be grouped as:

- Strategy Profile
- Risk Filters
- Breakeven Rules
- Earnings / IV Risk Rules
- Rejection Rules
- Checklist Rules
- Scan Schedule
- AI Provider Settings
- Memory Settings
- UI Display Mode