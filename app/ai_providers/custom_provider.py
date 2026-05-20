"""Custom provider for future expansion + a generic local-LLM provider
(Phase 17, step 17.12).

``CustomProvider`` is an OpenAI-compatible endpoint with fully user-supplied
config (base URL / model / optional key). ``LocalLlmProvider`` is the same shape
pointed at a local server with no API key required. Tests inject ``call_fn``.
"""

from __future__ import annotations

from app.ai_providers.openai_compatible_provider import OpenAiCompatibleProvider
from app.ai_providers.provider_types import CUSTOM, LOCAL_LLM


class CustomProvider(OpenAiCompatibleProvider):
    def __init__(
        self,
        *,
        model: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        api_key_env: str | None = "CUSTOM_PROVIDER_API_KEY",
        enabled: bool = False,
        requires_api_key: bool = False,
        call_fn=None,
    ) -> None:
        super().__init__(
            provider_type=CUSTOM,
            model=model,
            base_url=base_url,
            api_key=api_key,
            api_key_env=api_key_env,
            enabled=enabled,
            requires_api_key=requires_api_key,
            call_fn=call_fn,
        )


class LocalLlmProvider(OpenAiCompatibleProvider):
    def __init__(
        self,
        *,
        model: str = "local-model",
        base_url: str = "http://localhost:8080/v1",
        enabled: bool = False,
        call_fn=None,
    ) -> None:
        super().__init__(
            provider_type=LOCAL_LLM,
            model=model,
            base_url=base_url,
            api_key=None,
            api_key_env=None,
            enabled=enabled,
            requires_api_key=False,
            call_fn=call_fn,
        )


__all__ = ["CustomProvider", "LocalLlmProvider"]
