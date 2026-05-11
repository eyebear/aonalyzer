from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    app_name: str = "Ao Ao Analyzer"
    app_technical_name: str = "aoaoanalyzer"
    app_env: str = "local"
    app_debug: bool = True

    api_host: str = "0.0.0.0"
    api_port: int = 8000

    dashboard_host: str = "0.0.0.0"
    dashboard_port: int = 8501

    active_ai_provider: str = "DISABLED"
    fallback_ai_provider: str = "DISABLED"

    default_strategy_profile: str = "Balanced Research Default"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> AppSettings:
    return AppSettings()
