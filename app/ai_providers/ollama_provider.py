"""Ollama local-LLM provider (Phase 17, step 17.11).

Talks to a local Ollama server (no API key). The real HTTP call is lazy/guarded;
tests inject ``call_fn``.
"""

from __future__ import annotations

from app.ai_providers.openai_compatible_provider import post_json
from app.ai_providers.provider_base import AIRequest, HttpChatProvider
from app.ai_providers.provider_types import OLLAMA


class OllamaProvider(HttpChatProvider):
    def __init__(
        self,
        *,
        model: str = "llama3.1",
        base_url: str = "http://localhost:11434",
        enabled: bool = False,
        call_fn=None,
    ) -> None:
        super().__init__(
            OLLAMA,
            model=model,
            base_url=base_url,
            api_key=None,
            api_key_env=None,
            enabled=enabled,
            requires_api_key=False,
            call_fn=call_fn,
        )

    def _http_generate(self, request: AIRequest) -> str:  # pragma: no cover - network
        url = f"{(self.base_url or '').rstrip('/')}/api/generate"
        body = post_json(
            url,
            {
                "model": self.model,
                "prompt": request.rendered_prompt(),
                "stream": False,
            },
            headers={},
        )
        return body.get("response", "")


__all__ = ["OllamaProvider"]
