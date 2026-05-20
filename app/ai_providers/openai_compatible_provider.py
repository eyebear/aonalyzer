"""Generic OpenAI-compatible chat provider (Phase 17, step 17.10).

Works with any endpoint exposing ``/chat/completions`` (OpenAI, many local
servers, etc.). The real HTTP call is lazy/guarded; tests inject ``call_fn``.
"""

from __future__ import annotations

import json
from typing import Any
from urllib.request import Request, urlopen

from app.ai_providers.provider_base import AIRequest, HttpChatProvider
from app.ai_providers.provider_types import OPENAI_COMPATIBLE


def post_json(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    timeout: int = 30,
) -> dict[str, Any]:  # pragma: no cover - network
    data = json.dumps(payload).encode("utf-8")
    request = Request(url, data=data, headers={"Content-Type": "application/json", **headers})
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


class OpenAiCompatibleProvider(HttpChatProvider):
    def __init__(
        self,
        *,
        provider_type: str = OPENAI_COMPATIBLE,
        model: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        api_key_env: str | None = "OPENAI_API_KEY",
        enabled: bool = False,
        requires_api_key: bool = True,
        call_fn=None,
    ) -> None:
        super().__init__(
            provider_type,
            model=model,
            base_url=base_url,
            api_key=api_key,
            api_key_env=api_key_env,
            enabled=enabled,
            requires_api_key=requires_api_key,
            call_fn=call_fn,
        )

    def _http_generate(self, request: AIRequest) -> str:  # pragma: no cover - network
        messages = []
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})
        messages.append({"role": "user", "content": request.prompt})

        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        url = f"{(self.base_url or '').rstrip('/')}/chat/completions"
        body = post_json(
            url,
            {
                "model": self.model,
                "messages": messages,
                "max_tokens": request.max_tokens,
                "temperature": request.temperature,
            },
            headers,
        )
        return body["choices"][0]["message"]["content"]


__all__ = ["OpenAiCompatibleProvider", "post_json"]
