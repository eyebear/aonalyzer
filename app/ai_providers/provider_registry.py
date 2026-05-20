"""Provider registry (Phase 17, step 17.3).

Holds one instance per provider type and builds the default set from settings.
API keys are read from the environment by name (never persisted); when a key is
absent the provider is simply NOT_CONFIGURED / unavailable.
"""

from __future__ import annotations

import os
from typing import Any

from app.ai_providers.custom_provider import CustomProvider, LocalLlmProvider
from app.ai_providers.gemini_provider import GeminiProvider
from app.ai_providers.grok_provider import GrokProvider
from app.ai_providers.manual_paste_provider import FreeWebAiProvider, ManualPasteProvider
from app.ai_providers.ollama_provider import OllamaProvider
from app.ai_providers.openai_compatible_provider import OpenAiCompatibleProvider
from app.ai_providers.provider_base import AIProvider, DisabledProvider
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
)


class ProviderRegistry:
    def __init__(self, providers: dict[str, AIProvider]) -> None:
        self._providers = dict(providers)

    def get(self, provider_type: str) -> AIProvider:
        if provider_type not in self._providers:
            # Unknown types degrade to DISABLED rather than raising.
            return self._providers.get(DISABLED, DisabledProvider())
        return self._providers[provider_type]

    def has(self, provider_type: str) -> bool:
        return provider_type in self._providers

    def list_types(self) -> list[str]:
        return list(self._providers.keys())

    def statuses(self) -> dict[str, dict[str, Any]]:
        return {
            ptype: {
                "provider_type": ptype,
                "available": provider.is_available(),
                "model": provider.model,
            }
            for ptype, provider in self._providers.items()
        }


def build_default_registry(settings: Any) -> ProviderRegistry:
    providers: dict[str, AIProvider] = {
        DISABLED: DisabledProvider(),
        MANUAL_PASTE: ManualPasteProvider(),
        FREE_WEB_AI: FreeWebAiProvider(),
        GEMINI: GeminiProvider(
            model=getattr(settings, "gemini_model", "gemini-1.5-flash"),
            api_key=getattr(settings, "gemini_api_key", "") or os.environ.get("GEMINI_API_KEY", ""),
            enabled=True,
        ),
        GROK: GrokProvider(
            model=getattr(settings, "grok_model", "grok-2"),
            api_key=getattr(settings, "grok_api_key", "") or os.environ.get("GROK_API_KEY", ""),
            enabled=True,
        ),
        OPENAI_COMPATIBLE: OpenAiCompatibleProvider(
            model=getattr(settings, "openai_compatible_model", "gpt-4o-mini"),
            base_url=getattr(settings, "openai_compatible_base_url", "") or None,
            api_key=getattr(settings, "openai_compatible_api_key", "")
            or os.environ.get("OPENAI_API_KEY", ""),
            enabled=True,
        ),
        OLLAMA: OllamaProvider(
            model=getattr(settings, "ollama_model", "llama3.1"),
            base_url=getattr(settings, "ollama_base_url", "http://localhost:11434"),
            enabled=True,
        ),
        LOCAL_LLM: LocalLlmProvider(
            model=getattr(settings, "local_llm_model", "local-model"),
            base_url=getattr(settings, "local_llm_base_url", "http://localhost:8080/v1"),
            enabled=True,
        ),
        CUSTOM: CustomProvider(
            model=getattr(settings, "custom_provider_model", "") or None,
            base_url=getattr(settings, "custom_provider_base_url", "") or None,
            api_key=getattr(settings, "custom_provider_api_key", "") or None,
            enabled=True,
        ),
    }
    return ProviderRegistry(providers)


__all__ = ["ProviderRegistry", "build_default_registry"]
