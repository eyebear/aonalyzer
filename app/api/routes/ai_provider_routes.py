from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.ai_providers.ai_provider_models import AiProvider
from app.ai_providers.ai_provider_service import AiProviderService
from app.ai_providers.provider_manager import AIProviderManager
from app.ai_providers.provider_types import TASK_GENERAL
from app.database.connection import get_db_session

router = APIRouter(prefix="/api/ai-providers", tags=["ai-providers"])


class SetProviderRequest(BaseModel):
    provider_type: str


class GenerateRequest(BaseModel):
    task_type: str = TASK_GENERAL
    prompt: str
    system_prompt: str | None = None


def _provider_to_dict(provider: AiProvider) -> dict[str, Any]:
    return {
        "provider_key": provider.provider_key,
        "provider_type": provider.provider_type,
        "display_name": provider.display_name,
        "is_enabled": provider.is_enabled,
        "is_active": provider.is_active,
        "is_fallback": provider.is_fallback,
        "base_url": provider.base_url,
        "model": provider.model,
        "api_key_env": provider.api_key_env,  # name only, never the key
    }


def _manager_for(service: AiProviderService, session: Session) -> AIProviderManager:
    return AIProviderManager(
        active_type=service.get_active(session),
        fallback_type=service.get_fallback(session),
    )


@router.get("")
def list_providers(session: Session = Depends(get_db_session)) -> dict[str, Any]:
    service = AiProviderService()
    providers = service.list_providers(session)
    return {
        "status": "OK",
        "count": len(providers),
        "active_provider": service.get_active(session),
        "fallback_provider": service.get_fallback(session),
        "providers": [_provider_to_dict(p) for p in providers],
    }


@router.get("/status")
def provider_status(session: Session = Depends(get_db_session)) -> dict[str, Any]:
    service = AiProviderService()
    manager = _manager_for(service, session)
    return {"status": "OK", **manager.get_status()}


@router.post("/active")
def set_active(
    request: SetProviderRequest,
    session: Session = Depends(get_db_session),
) -> dict[str, Any]:
    service = AiProviderService()
    try:
        provider = service.set_active(session, request.provider_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "OK", "active_provider": provider.provider_key}


@router.post("/fallback")
def set_fallback(
    request: SetProviderRequest,
    session: Session = Depends(get_db_session),
) -> dict[str, Any]:
    service = AiProviderService()
    try:
        provider = service.set_fallback(session, request.provider_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "OK", "fallback_provider": provider.provider_key}


@router.post("/generate")
def generate(
    request: GenerateRequest,
    session: Session = Depends(get_db_session),
) -> dict[str, Any]:
    service = AiProviderService()
    manager = _manager_for(service, session)
    response = manager.generate(
        request.task_type,
        request.prompt,
        system_prompt=request.system_prompt,
    )
    return {"status": "OK", "response": response.to_dict()}
