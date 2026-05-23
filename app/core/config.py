from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    app_name: str = "Aonalyzer"
    app_technical_name: str = "aonalyzer"
    app_env: str = "local"
    app_debug: bool = True

    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_base_url: str = "http://localhost:8000"

    dashboard_host: str = "0.0.0.0"
    dashboard_port: int = 8501

    postgres_host: str = "localhost"
    postgres_port: int = 5434
    postgres_db: str = "aonalyzer"
    postgres_user: str = "aonalyzer"
    postgres_password: str = "aonalyzer_password"
    database_url: str = (
        "postgresql+psycopg://aonalyzer:aonalyzer_password"
        "@localhost:5434/aonalyzer"
    )

    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_url: str = "redis://localhost:6379/0"

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1"

    active_ai_provider: str = "DISABLED"
    fallback_ai_provider: str = "DISABLED"

    default_strategy_profile: str = "Balanced Research Default"

    market_data_refresh_minutes: int = 30
    option_chain_refresh_minutes: int = 60
    news_refresh_minutes: int = 60
    watchlist_news_refresh_minutes: int = 30
    filing_refresh_minutes: int = 60
    iv_risk_refresh_minutes: int = 60

    # --- Phase 13: Market Regime & Sector Strength ---
    # All symbol lists and thresholds ship with defaults but are overridable via
    # environment variables (complex types accept a JSON-encoded value).
    market_regime_index_symbols: list[str] = ["SPY", "QQQ", "IWM"]
    market_regime_vix_symbol: str = "^VIX"
    market_regime_yield_symbol: str = "^TNX"
    market_regime_sector_etfs: list[str] = ["XLK", "XLF", "XLE", "SMH", "SOXX"]
    market_regime_benchmark_symbols: list[str] = ["SPY", "QQQ"]

    # Trend (fast/slow SMA) and relative-strength lookback windows (trading days).
    market_regime_trend_fast_period: int = 20
    market_regime_trend_slow_period: int = 50
    market_regime_rs_lookback_days: int = 20
    # Minimum daily-price rows required before a trend is computed (else INSUFFICIENT).
    market_regime_min_price_rows: int = 50

    # VIX state bands: <= calm is RISK_ON-leaning, >= stress is RISK_OFF-leaning.
    market_regime_vix_calm_threshold: float = 15.0
    market_regime_vix_stress_threshold: float = 25.0

    # 10Y yield pressure. ``yield_level`` is the raw close of the yield symbol
    # (``^TNX`` is interpreted as percentage points, e.g. 4.5). Pressure triggers
    # when the yield is rising by at least ``rise_pct`` over the lookback OR the
    # level is at/above ``level``. ``rise_pct`` is scale-invariant.
    market_regime_yield_pressure_level: float = 4.5
    market_regime_yield_rise_pct: float = 0.10
    market_regime_yield_refresh_minutes: int = 60

    # --- Phase 14: Stock Setup Detection ---
    # Classification thresholds (all overridable via environment variables).
    setup_rsi_oversold: float = 30.0
    setup_rsi_pullback_ceiling: float = 55.0
    setup_pullback_atr_mult: float = 0.5
    setup_breakout_retest_tolerance: float = 0.03
    setup_breakdown_tolerance: float = 0.01
    setup_min_risk_reward: float = 2.0
    setup_sector_strong_max_rank: int = 2
    setup_volume_confirm_ratio: float = 1.2
    # Optional ticker -> sector ETF map enabling SECTOR_STRENGTH_LONG detection.
    # Empty by default (no per-ticker sector data is invented); override via a
    # JSON env value, e.g. {"NVDA": "SMH", "AMD": "SMH"}.
    setup_sector_map: dict[str, str] = {}

    # --- Phase 15: Optional Option Suitability Engine ---
    # Profile supplies DTE / premium / IV / target-breakeven thresholds; these
    # cover the remaining filter knobs (all overridable via environment).
    option_suitability_enabled: bool = True
    option_max_spread_percent: float = 10.0
    option_min_open_interest: int = 100
    option_min_volume_preference: int = 10
    option_max_breakeven_distance_percent: float = 12.0
    option_iv_fraction_cutoff: float = 5.0

    # --- Phase 16: Pretrained Model Layer Foundation ---
    # Master switch: when False (default) the system runs in fallback mode and
    # never loads a real model -- adapters return deterministic fallback output.
    models_enabled: bool = False
    finbert_model_name: str = "ProsusAI/finbert"
    fingpt_model_name: str = "FinGPT"
    kronos_model_name: str = "Kronos"
    embeddings_model_name: str = "sentence-transformers/all-MiniLM-L6-v2"

    # --- Phase 17: AI Provider Manager ---
    # active_ai_provider / fallback_ai_provider already exist (default DISABLED).
    # API keys default empty -> providers stay NOT_CONFIGURED until set. Keys may
    # also be supplied via the matching environment variable.
    gemini_api_key: str = ""
    gemini_model: str = "gemini-1.5-flash"
    grok_api_key: str = ""
    grok_model: str = "grok-2"
    openai_compatible_api_key: str = ""
    openai_compatible_base_url: str = ""
    openai_compatible_model: str = "gpt-4o-mini"
    local_llm_base_url: str = "http://localhost:8080/v1"
    local_llm_model: str = "local-model"
    custom_provider_base_url: str = ""
    custom_provider_api_key: str = ""
    custom_provider_model: str = ""

    # --- Phase 18: AI Event & Manual Option Text Analysis ---
    # Only analyze events at/above this importance to control AI cost.
    event_analysis_min_importance: str = "HIGH"

    # --- Phase 20: Hard Filter Gate ---
    # Stock thesis -- minimum risk/reward used by the hard filter when no
    # profile override is supplied; the profile's ``minimum_risk_reward``
    # normally drives it.
    hard_filter_min_stock_risk_reward: float = 2.0
    # Price extension: a long is "chasing" when spot is too far above the
    # nearest support relative to ATR. ``None`` for either threshold disables
    # that specific check. Defaults are deliberately conservative; profiles
    # may override later in Phase 22+.
    hard_filter_max_atr_extension_multiple: float = 3.0
    hard_filter_max_sma50_extension_percent: float = 15.0
    # Earnings risk: when ``True`` (default) earnings inside the profile's
    # risk window is a warning; when option expiration falls before
    # earnings it is a hard fail. Profiles cannot bypass this.
    hard_filter_earnings_inside_window_blocks: bool = False

    # --- Phase 47: Settings (manual option behavior) ---
    # Safe defaults: missing option data must never block stock-only research,
    # so ``allow_stock_only_when_options_missing`` stays True by default.
    manual_option_input_enabled: bool = True
    option_text_ai_reader_enabled: bool = True
    strict_option_parser_mode: bool = False
    allow_stock_only_when_options_missing: bool = True

    exports_dir: str = "exports"
    models_dir: str = "models"
    reports_dir: str = "reports"
    data_dir: str = "data"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> AppSettings:
    return AppSettings()