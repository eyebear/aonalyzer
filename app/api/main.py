from fastapi import FastAPI

from app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    description=(
        "Local, Dockerized, AI-assisted equity and options research operating system. "
        "Research-only. No broker integration. No auto-trading."
    ),
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
        "research_only": True,
        "broker_connected": False,
        "auto_trading_enabled": False,
        "active_ai_provider": settings.active_ai_provider,
        "default_strategy_profile": settings.default_strategy_profile,
    }
