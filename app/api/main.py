from fastapi import FastAPI

from app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    description="Local equity and options research platform.",
    version="0.1.0",
)


@app.get("/health")
def health_check() -> dict:
    return {
        "status": "ok",
        "app_name": settings.app_name,
        "technical_name": settings.app_technical_name,
        "environment": settings.app_env,
    }


@app.get("/api/system/status")
def system_status() -> dict:
    return {
        "status": "starting",
        "app_name": settings.app_name,
        "technical_name": settings.app_technical_name,
        "environment": settings.app_env,
        "active_ai_provider": settings.active_ai_provider,
        "default_strategy_profile": settings.default_strategy_profile,
        "postgres_host": settings.postgres_host,
        "postgres_port": settings.postgres_port,
        "redis_host": settings.redis_host,
        "redis_port": settings.redis_port,
    }