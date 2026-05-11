from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    app_name: str = "Ao Ao Analyzer"
    app_technical_name: str = "aoaoanalyzer"
    app_env: str = "local"
    app_debug: bool = True

    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_base_url: str = "http://localhost:8000"

    dashboard_host: str = "0.0.0.0"
    dashboard_port: int = 8501

    postgres_host: str = "localhost"
    postgres_port: int = 5434
    postgres_db: str = "aoaoanalyzer"
    postgres_user: str = "aoaoanalyzer"
    postgres_password: str = "aoaoanalyzer_password"
    database_url: str = (
        "postgresql+psycopg://aoaoanalyzer:aoaoanalyzer_password"
        "@localhost:5434/aoaoanalyzer"
    )

    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_url: str = "redis://localhost:6379/0"

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1"

    active_ai_provider: str = "DISABLED"
    fallback_ai_provider: str = "DISABLED"

    default_strategy_profile: str = "Balanced Research Default"

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