"""Grok (xAI) provider (Phase 17, step 17.9).

xAI exposes an OpenAI-compatible API, so this reuses the OpenAI-compatible flow
with Grok defaults. Tests inject ``call_fn``; no network is touched.
"""

from __future__ import annotations

from app.ai_providers.openai_compatible_provider import OpenAiCompatibleProvider
from app.ai_providers.provider_types import GROK


class GrokProvider(OpenAiCompatibleProvider):
    def __init__(
        self,
        *,
        model: str = "grok-2",
        api_key: str | None = None,
        base_url: str = "https://api.x.ai/v1",
        enabled: bool = False,
        call_fn=None,
    ) -> None:
        super().__init__(
            provider_type=GROK,
            model=model,
            base_url=base_url,
            api_key=api_key,
            api_key_env="GROK_API_KEY",
            enabled=enabled,
            requires_api_key=True,
            call_fn=call_fn,
        )


__all__ = ["GrokProvider"]
