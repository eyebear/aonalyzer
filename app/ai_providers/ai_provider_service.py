"""Persistence for AI provider configuration (Phase 17, step 17.13).

Seeds the default provider rows and manages the active/fallback selection that
the settings UI drives. API keys are never stored -- only the env-var name.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.ai_providers.ai_provider_models import AiProvider
from app.ai_providers.provider_types import (
    CUSTOM,
    DISABLED,
    FREE_WEB_AI,
    GEMINI,
    GROK,
    LOCAL_LLM,
    MANUAL_PASTE,
    OLLAMA,
    OPENAI_COMPATIBLE,
    is_valid_provider_type,
)
from app.common.service_utils import ensure_tables
from app.core.config import AppSettings, get_settings


def _default_rows(settings: AppSettings) -> list[dict[str, Any]]:
    return [
        {
            "provider_type": DISABLED,
            "display_name": "Disabled",
            "is_enabled": True,
            "base_url": None,
            "model": None,
            "api_key_env": None,
        },
        {
            "provider_type": MANUAL_PASTE,
            "display_name": "Manual Paste",
            "is_enabled": True,
            "base_url": None,
            "model": None,
            "api_key_env": None,
        },
        {
            "provider_type": FREE_WEB_AI,
            "display_name": "Free Web AI",
            "is_enabled": True,
            "base_url": None,
            "model": None,
            "api_key_env": None,
        },
        {
            "provider_type": GEMINI,
            "display_name": "Google Gemini",
            "is_enabled": True,
            "base_url": None,
            "model": settings.gemini_model,
            "api_key_env": "GEMINI_API_KEY",
        },
        {
            "provider_type": GROK,
            "display_name": "Grok (xAI)",
            "is_enabled": True,
            "base_url": "https://api.x.ai/v1",
            "model": settings.grok_model,
            "api_key_env": "GROK_API_KEY",
        },
        {
            "provider_type": OPENAI_COMPATIBLE,
            "display_name": "OpenAI-compatible",
            "is_enabled": True,
            "base_url": settings.openai_compatible_base_url or None,
            "model": settings.openai_compatible_model,
            "api_key_env": "OPENAI_API_KEY",
        },
        {
            "provider_type": OLLAMA,
            "display_name": "Ollama (local)",
            "is_enabled": True,
            "base_url": settings.ollama_base_url,
            "model": settings.ollama_model,
            "api_key_env": None,
        },
        {
            "provider_type": LOCAL_LLM,
            "display_name": "Local LLM",
            "is_enabled": True,
            "base_url": settings.local_llm_base_url,
            "model": settings.local_llm_model,
            "api_key_env": None,
        },
        {
            "provider_type": CUSTOM,
            "display_name": "Custom",
            "is_enabled": True,
            "base_url": settings.custom_provider_base_url or None,
            "model": settings.custom_provider_model or None,
            "api_key_env": "CUSTOM_PROVIDER_API_KEY",
        },
    ]


class AiProviderService:
    def __init__(self, settings: AppSettings | None = None) -> None:
        self.settings = settings or get_settings()

    def ensure_tables(self, db: Session) -> None:
        ensure_tables(db)

    def seed_default_providers(self, db: Session) -> int:
        self.ensure_tables(db)
        existing = {p.provider_key for p in db.query(AiProvider).all()}
        active = self.settings.active_ai_provider
        fallback = self.settings.fallback_ai_provider

        created = 0
        for row in _default_rows(self.settings):
            key = row["provider_type"]
            if key in existing:
                continue
            db.add(
                AiProvider(
                    provider_key=key,
                    provider_type=row["provider_type"],
                    display_name=row["display_name"],
                    is_enabled=row["is_enabled"],
                    is_active=(key == active),
                    is_fallback=(key == fallback),
                    base_url=row["base_url"],
                    model=row["model"],
                    api_key_env=row["api_key_env"],
                )
            )
            created += 1
        db.commit()
        return created

    def list_providers(self, db: Session) -> list[AiProvider]:
        self.ensure_tables(db)
        self.seed_default_providers(db)
        return db.query(AiProvider).order_by(AiProvider.id.asc()).all()

    def set_active(self, db: Session, provider_type: str) -> AiProvider:
        return self._set_flag(db, provider_type, "is_active")

    def set_fallback(self, db: Session, provider_type: str) -> AiProvider:
        return self._set_flag(db, provider_type, "is_fallback")

    def get_active(self, db: Session) -> str:
        return self._get_flagged(db, "is_active", self.settings.active_ai_provider)

    def get_fallback(self, db: Session) -> str:
        return self._get_flagged(db, "is_fallback", self.settings.fallback_ai_provider)

    def _set_flag(self, db: Session, provider_type: str, flag: str) -> AiProvider:
        if not is_valid_provider_type(provider_type):
            raise ValueError(f"Unknown provider type: {provider_type}")
        self.seed_default_providers(db)

        rows = db.query(AiProvider).all()
        target = None
        for row in rows:
            setattr(row, flag, row.provider_key == provider_type)
            if row.provider_key == provider_type:
                target = row
        db.commit()
        if target is None:
            raise ValueError(f"Provider {provider_type} not found.")
        db.refresh(target)
        return target

    def _get_flagged(self, db: Session, flag: str, default: str) -> str:
        self.seed_default_providers(db)
        row = (
            db.query(AiProvider)
            .filter(getattr(AiProvider, flag).is_(True))
            .order_by(AiProvider.id.asc())
            .first()
        )
        return row.provider_key if row is not None else default


__all__ = ["AiProviderService"]
