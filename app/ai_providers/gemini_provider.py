"""Google Gemini provider (Phase 17, step 17.8).

Uses the Gemini ``generateContent`` REST endpoint. The real HTTP call is
lazy/guarded; tests inject ``call_fn`` so no network/key is needed.
"""

from __future__ import annotations

from app.ai_providers.openai_compatible_provider import post_json
from app.ai_providers.provider_base import AIRequest, HttpChatProvider
from app.ai_providers.provider_types import GEMINI


class GeminiProvider(HttpChatProvider):
    def __init__(
        self,
        *,
        model: str = "gemini-1.5-flash",
        api_key: str | None = None,
        base_url: str = "https://generativelanguage.googleapis.com/v1beta",
        enabled: bool = False,
        call_fn=None,
    ) -> None:
        super().__init__(
            GEMINI,
            model=model,
            base_url=base_url,
            api_key=api_key,
            api_key_env="GEMINI_API_KEY",
            enabled=enabled,
            requires_api_key=True,
            call_fn=call_fn,
        )

    def _http_generate(self, request: AIRequest) -> str:  # pragma: no cover - network
        url = (
            f"{(self.base_url or '').rstrip('/')}/models/{self.model}:generateContent"
            f"?key={self.api_key}"
        )
        body = post_json(
            url,
            {"contents": [{"parts": [{"text": request.rendered_prompt()}]}]},
            headers={},
        )
        return body["candidates"][0]["content"]["parts"][0]["text"]


__all__ = ["GeminiProvider"]
