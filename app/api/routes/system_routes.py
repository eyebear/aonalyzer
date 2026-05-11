from fastapi import APIRouter

from app.api.dto import SystemStatusResponse
from app.core.config import get_settings

router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/status", response_model=SystemStatusResponse)
def system_status() -> SystemStatusResponse:
    settings = get_settings()

    return SystemStatusResponse(
        status="running",
        app_name=settings.app_name,
        technical_name=settings.app_technical_name,
        environment=settings.app_env,
        active_ai_provider=settings.active_ai_provider,
        default_strategy_profile=settings.default_strategy_profile,
        postgres_host=settings.postgres_host,
        postgres_port=settings.postgres_port,
        redis_host=settings.redis_host,
        redis_port=settings.redis_port,
    )