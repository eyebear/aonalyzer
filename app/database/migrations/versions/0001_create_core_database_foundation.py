"""create core database foundation

Revision ID: 0001_create_core_database_foundation
Revises:
Create Date: 2026-05-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_core_foundation"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # pgvector is OPTIONAL. No table in this schema uses a native ``vector``
    # column (embeddings are stored as portable JSON — see
    # ``app.memory.memory_embedding_models``). Enable the extension only when
    # the server actually ships it (e.g. the ``pgvector/pgvector:pg16`` image
    # used by docker-compose); degrade cleanly on vanilla PostgreSQL such as
    # the ``postgres:16`` CI service container.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_available_extensions WHERE name = 'vector'
            ) THEN
                CREATE EXTENSION IF NOT EXISTS vector;
            END IF;
        END
        $$;
        """
    )

    op.create_table(
        "tickers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("market", sa.String(length=32), nullable=False),
        sa.Column("asset_type", sa.String(length=32), nullable=False),
        sa.Column("currency", sa.String(length=16), nullable=False, server_default="USD"),
        sa.Column("exchange", sa.String(length=64), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("symbol", name="uq_tickers_symbol"),
    )
    op.create_index("ix_tickers_symbol", "tickers", ["symbol"])

    op.create_table(
        "watchlists",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ticker_id", sa.Integer(), sa.ForeignKey("tickers.id"), nullable=False),
        sa.Column("watchlist_name", sa.String(length=128), nullable=False, server_default="Default"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("ticker_id", "watchlist_name", name="uq_watchlists_ticker_name"),
    )

    op.create_table(
        "daily_prices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("price_date", sa.Date(), nullable=False),
        sa.Column("open_price", sa.Numeric(18, 6), nullable=True),
        sa.Column("high_price", sa.Numeric(18, 6), nullable=True),
        sa.Column("low_price", sa.Numeric(18, 6), nullable=True),
        sa.Column("close_price", sa.Numeric(18, 6), nullable=True),
        sa.Column("adjusted_close_price", sa.Numeric(18, 6), nullable=True),
        sa.Column("volume", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(length=64), nullable=False, server_default="yfinance"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("symbol", "price_date", name="uq_daily_prices_symbol_date"),
    )
    op.create_index("ix_daily_prices_symbol", "daily_prices", ["symbol"])
    op.create_index("ix_daily_prices_symbol_date", "daily_prices", ["symbol", "price_date"])

    op.create_table(
        "intraday_prices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("price_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("interval", sa.String(length=16), nullable=False),
        sa.Column("open_price", sa.Numeric(18, 6), nullable=True),
        sa.Column("high_price", sa.Numeric(18, 6), nullable=True),
        sa.Column("low_price", sa.Numeric(18, 6), nullable=True),
        sa.Column("close_price", sa.Numeric(18, 6), nullable=True),
        sa.Column("volume", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(length=64), nullable=False, server_default="yfinance"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "symbol",
            "price_time",
            "interval",
            name="uq_intraday_prices_symbol_time_interval",
        ),
    )
    op.create_index("ix_intraday_prices_symbol", "intraday_prices", ["symbol"])
    op.create_index("ix_intraday_prices_symbol_time", "intraday_prices", ["symbol", "price_time"])

    op.create_table(
        "events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("detected_time", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("source", sa.String(length=128), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("source_title", sa.Text(), nullable=True),
        sa.Column("symbol", sa.String(length=32), nullable=True),
        sa.Column("market", sa.String(length=32), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("importance_level", sa.String(length=32), nullable=False, server_default="LOW"),
        sa.Column("headline", sa.Text(), nullable=False),
        sa.Column("raw_summary", sa.Text(), nullable=True),
        sa.Column("content_hash", sa.String(length=128), nullable=True),
        sa.Column("event_metadata_json", sa.JSON(), nullable=True),
        sa.Column("is_reviewed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("content_hash", name="uq_events_content_hash"),
    )
    op.create_index("ix_events_symbol", "events", ["symbol"])
    op.create_index("ix_events_symbol_event_time", "events", ["symbol", "event_time"])
    op.create_index("ix_events_type_importance", "events", ["event_type", "importance_level"])

    op.create_table(
        "agent_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("job_name", sa.String(length=128), nullable=False),
        sa.Column("job_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Numeric(18, 3), nullable=True),
        sa.Column("triggered_by", sa.String(length=32), nullable=False),
        sa.Column("trigger_source", sa.String(length=64), nullable=False),
        sa.Column("symbols_processed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_created", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_updated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_agent_runs_job_name", "agent_runs", ["job_name"])

    op.create_table(
        "scan_schedule_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("setting_name", sa.String(length=128), nullable=False),
        sa.Column("refresh_minutes", sa.Integer(), nullable=True),
        sa.Column("schedule_value", sa.String(length=128), nullable=True),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("setting_name", name="uq_scan_schedule_settings_name"),
    )

    op.create_table(
        "default_strategy_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("profile_name", sa.String(length=128), nullable=False),
        sa.Column("profile_type", sa.String(length=64), nullable=False),
        sa.Column("profile_version", sa.String(length=128), nullable=False),
        sa.Column("profile_json", sa.JSON(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("profile_name", name="uq_default_strategy_profiles_name"),
    )

    op.create_table(
        "version_registry",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("version_key", sa.String(length=128), nullable=False),
        sa.Column("version_value", sa.String(length=128), nullable=False),
        sa.Column("version_type", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("version_key", name="uq_version_registry_key"),
    )

    op.create_table(
        "strategy_profile_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("profile_name", sa.String(length=128), nullable=False),
        sa.Column("profile_version", sa.String(length=128), nullable=False),
        sa.Column("profile_type", sa.String(length=64), nullable=False),
        sa.Column("profile_json", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "profile_name",
            "profile_version",
            name="uq_strategy_profile_versions_name_version",
        ),
    )

    tickers_table = sa.table(
        "tickers",
        sa.column("symbol", sa.String),
        sa.column("name", sa.String),
        sa.column("market", sa.String),
        sa.column("asset_type", sa.String),
        sa.column("currency", sa.String),
        sa.column("exchange", sa.String),
        sa.column("is_active", sa.Boolean),
    )

    initial_tickers = [
        {"symbol": "AAPL", "name": "Apple Inc.", "market": "US", "asset_type": "STOCK", "currency": "USD", "exchange": "NASDAQ", "is_active": True},
        {"symbol": "MSFT", "name": "Microsoft Corporation", "market": "US", "asset_type": "STOCK", "currency": "USD", "exchange": "NASDAQ", "is_active": True},
        {"symbol": "NVDA", "name": "NVIDIA Corporation", "market": "US", "asset_type": "STOCK", "currency": "USD", "exchange": "NASDAQ", "is_active": True},
        {"symbol": "AMD", "name": "Advanced Micro Devices, Inc.", "market": "US", "asset_type": "STOCK", "currency": "USD", "exchange": "NASDAQ", "is_active": True},
        {"symbol": "TSLA", "name": "Tesla, Inc.", "market": "US", "asset_type": "STOCK", "currency": "USD", "exchange": "NASDAQ", "is_active": True},
        {"symbol": "SPY", "name": "SPDR S&P 500 ETF Trust", "market": "US", "asset_type": "ETF", "currency": "USD", "exchange": "NYSEARCA", "is_active": True},
        {"symbol": "QQQ", "name": "Invesco QQQ Trust", "market": "US", "asset_type": "ETF", "currency": "USD", "exchange": "NASDAQ", "is_active": True},
        {"symbol": "IWM", "name": "iShares Russell 2000 ETF", "market": "US", "asset_type": "ETF", "currency": "USD", "exchange": "NYSEARCA", "is_active": True},
        {"symbol": "SHOP.TO", "name": "Shopify Inc.", "market": "Canada", "asset_type": "STOCK", "currency": "CAD", "exchange": "TSX", "is_active": True},
        {"symbol": "RY.TO", "name": "Royal Bank of Canada", "market": "Canada", "asset_type": "STOCK", "currency": "CAD", "exchange": "TSX", "is_active": True},
        {"symbol": "TD.TO", "name": "The Toronto-Dominion Bank", "market": "Canada", "asset_type": "STOCK", "currency": "CAD", "exchange": "TSX", "is_active": True},
        {"symbol": "ENB.TO", "name": "Enbridge Inc.", "market": "Canada", "asset_type": "STOCK", "currency": "CAD", "exchange": "TSX", "is_active": True},
    ]
    op.bulk_insert(tickers_table, initial_tickers)

    op.execute(
        """
        INSERT INTO watchlists (ticker_id, watchlist_name, is_active)
        SELECT id, 'Default', true
        FROM tickers
        """
    )

    scan_schedule_settings_table = sa.table(
        "scan_schedule_settings",
        sa.column("setting_name", sa.String),
        sa.column("refresh_minutes", sa.Integer),
        sa.column("schedule_value", sa.String),
        sa.column("is_enabled", sa.Boolean),
    )
    op.bulk_insert(
        scan_schedule_settings_table,
        [
            {"setting_name": "market_data_refresh", "refresh_minutes": 30, "schedule_value": "market_hours", "is_enabled": True},
            {"setting_name": "option_chain_refresh", "refresh_minutes": 60, "schedule_value": "market_hours", "is_enabled": True},
            {"setting_name": "news_refresh", "refresh_minutes": 60, "schedule_value": "always", "is_enabled": True},
            {"setting_name": "watchlist_news_refresh", "refresh_minutes": 30, "schedule_value": "always", "is_enabled": True},
            {"setting_name": "filing_refresh", "refresh_minutes": 60, "schedule_value": "always", "is_enabled": True},
            {"setting_name": "earnings_calendar_refresh", "refresh_minutes": None, "schedule_value": "daily", "is_enabled": True},
            {"setting_name": "iv_risk_refresh", "refresh_minutes": 60, "schedule_value": "market_hours", "is_enabled": True},
        ],
    )

    balanced_profile_json = {
        "profile_name": "Balanced Research Default",
        "profile_type": "BALANCED",
        "profile_version": "balanced_research_default_1.0",
        "stock_thesis_horizon_min_trading_days": 10,
        "stock_thesis_horizon_max_trading_days": 25,
        "option_dte_min": 45,
        "option_dte_max": 90,
        "premium_min_usd": 500,
        "premium_max_usd": 1000,
        "minimum_risk_reward": 2.0,
        "reject_if_target_below_breakeven": True,
        "minimum_target_breakeven_margin_percent": 3.0,
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
        "hard_filters_can_be_bypassed": False,
    }

    default_strategy_profiles_table = sa.table(
        "default_strategy_profiles",
        sa.column("profile_name", sa.String),
        sa.column("profile_type", sa.String),
        sa.column("profile_version", sa.String),
        sa.column("profile_json", sa.JSON),
        sa.column("is_default", sa.Boolean),
        sa.column("is_active", sa.Boolean),
    )
    op.bulk_insert(
        default_strategy_profiles_table,
        [
            {
                "profile_name": "Balanced Research Default",
                "profile_type": "BALANCED",
                "profile_version": "balanced_research_default_1.0",
                "profile_json": balanced_profile_json,
                "is_default": True,
                "is_active": True,
            }
        ],
    )

    strategy_profile_versions_table = sa.table(
        "strategy_profile_versions",
        sa.column("profile_name", sa.String),
        sa.column("profile_version", sa.String),
        sa.column("profile_type", sa.String),
        sa.column("profile_json", sa.JSON),
        sa.column("is_active", sa.Boolean),
    )
    op.bulk_insert(
        strategy_profile_versions_table,
        [
            {
                "profile_name": "Balanced Research Default",
                "profile_version": "balanced_research_default_1.0",
                "profile_type": "BALANCED",
                "profile_json": balanced_profile_json,
                "is_active": True,
            }
        ],
    )

    version_registry_table = sa.table(
        "version_registry",
        sa.column("version_key", sa.String),
        sa.column("version_value", sa.String),
        sa.column("version_type", sa.String),
        sa.column("description", sa.Text),
        sa.column("is_active", sa.Boolean),
    )
    op.bulk_insert(
        version_registry_table,
        [
            {"version_key": "rule_version", "version_value": "ruleset_2026_05_v1", "version_type": "RULE", "description": "Initial rule version.", "is_active": True},
            {"version_key": "strategy_profile_version", "version_value": "balanced_research_default_1.0", "version_type": "STRATEGY_PROFILE", "description": "Initial profile version.", "is_active": True},
            {"version_key": "data_schema_version", "version_value": "aoao_schema_0.1", "version_type": "DATA_SCHEMA", "description": "Initial database schema version.", "is_active": True},
            {"version_key": "decision_engine_version", "version_value": "decision_engine_0.1", "version_type": "DECISION_ENGINE", "description": "Initial decision engine placeholder version.", "is_active": True},
            {"version_key": "action_suggestion_version", "version_value": "action_suggestion_0.1", "version_type": "ACTION_SUGGESTION", "description": "Initial action suggestion placeholder version.", "is_active": True},
        ],
    )


def downgrade() -> None:
    op.drop_table("strategy_profile_versions")
    op.drop_table("version_registry")
    op.drop_table("default_strategy_profiles")
    op.drop_table("scan_schedule_settings")
    op.drop_index("ix_agent_runs_job_name", table_name="agent_runs")
    op.drop_table("agent_runs")
    op.drop_index("ix_events_type_importance", table_name="events")
    op.drop_index("ix_events_symbol_event_time", table_name="events")
    op.drop_index("ix_events_symbol", table_name="events")
    op.drop_table("events")
    op.drop_index("ix_intraday_prices_symbol_time", table_name="intraday_prices")
    op.drop_index("ix_intraday_prices_symbol", table_name="intraday_prices")
    op.drop_table("intraday_prices")
    op.drop_index("ix_daily_prices_symbol_date", table_name="daily_prices")
    op.drop_index("ix_daily_prices_symbol", table_name="daily_prices")
    op.drop_table("daily_prices")
    op.drop_table("watchlists")
    op.drop_index("ix_tickers_symbol", table_name="tickers")
    op.drop_table("tickers")