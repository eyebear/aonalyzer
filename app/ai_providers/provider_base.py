"""Common provider interface + base classes (Phase 17, step 17.1).

Defines the request/response schema every provider shares, the ``AIProvider``
abstract base, a ``DisabledProvider``, and an ``HttpChatProvider`` base for the
network-backed providers. Network calls are lazy and guarded; an injectable
``call_fn`` lets tests run fully offline. Providers never raise from
``generate`` -- they return an ``AIResponse`` with an explicit status.
"""

from __future__ import annotations

import abc
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.ai_providers.provider_types import (
    ERROR,
    NOT_CONFIGURED,
    OK,
    STATUS_DISABLED,
    UNAVAILABLE,
)

# A mock/real generator: takes the request, returns generated text.
CallFn = Callable[["AIRequest"], str]


@dataclass(frozen=True)
class AIRequest:
    task_type: str
    prompt: str
    system_prompt: str | None = None
    max_tokens: int = 1024
    temperature: float = 0.2
    metadata: dict[str, Any] = field(default_factory=dict)

    def rendered_prompt(self) -> str:
        if self.system_prompt:
            return f"{self.system_prompt}\n\n{self.prompt}"
        return self.prompt


@dataclass(frozen=True)
class AIResponse:
    status: str
    provider_type: str
    task_type: str
    text: str | None = None
    model: str | None = None
    fallback_reason: str | None = None
    manual_prompt: str | None = None
    raw: dict[str, Any] | None = None

    @property
    def is_ok(self) -> bool:
        return self.status == OK

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "provider_type": self.provider_type,
            "task_type": self.task_type,
            "text": self.text,
            "model": self.model,
            "fallback_reason": self.fallback_reason,
            "manual_prompt": self.manual_prompt,
            "is_ok": self.is_ok,
        }


@dataclass(frozen=True)
class ProviderHealth:
    provider_type: str
    healthy: bool
    status: str
    detail: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_type": self.provider_type,
            "healthy": self.healthy,
            "status": self.status,
            "detail": self.detail,
        }


class AIProvider(abc.ABC):
    provider_type: str = "BASE"
    model: str | None = None

    @abc.abstractmethod
    def is_available(self) -> bool:
        ...

    @abc.abstractmethod
    def generate(self, request: AIRequest) -> AIResponse:
        ...

    def health_check(self) -> ProviderHealth:
        available = self.is_available()
        return ProviderHealth(
            provider_type=self.provider_type,
            healthy=available,
            status="OK" if available else "UNAVAILABLE",
            detail=None if available else "Provider is not available.",
        )

    def _response(self, status: str, **kwargs: Any) -> AIResponse:
        return AIResponse(
            status=status,
            provider_type=self.provider_type,
            task_type=kwargs.pop("task_type"),
            **kwargs,
        )


class DisabledProvider(AIProvider):
    provider_type = STATUS_DISABLED

    def is_available(self) -> bool:
        return False

    def generate(self, request: AIRequest) -> AIResponse:
        return self._response(
            STATUS_DISABLED,
            task_type=request.task_type,
            fallback_reason="AI is disabled; the system runs without it.",
        )


class HttpChatProvider(AIProvider):
    """Base for network-backed chat providers.

    Concrete subclasses set defaults and may override ``_http_generate`` for the
    real API call. Tests inject ``call_fn`` so no network is touched.
    """

    def __init__(
        self,
        provider_type: str,
        *,
        model: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        api_key_env: str | None = None,
        enabled: bool = False,
        requires_api_key: bool = True,
        call_fn: CallFn | None = None,
    ) -> None:
        self.provider_type = provider_type
        self.model = model
        self.base_url = base_url
        self.api_key = api_key
        self.api_key_env = api_key_env
        self.enabled = enabled
        self.requires_api_key = requires_api_key
        self._call_fn = call_fn

    def is_available(self) -> bool:
        if self._call_fn is not None:
            return self.enabled
        if not self.enabled:
            return False
        if self.requires_api_key and not self.api_key:
            return False
        if not self.requires_api_key and not self.base_url:
            return False
        return True

    def generate(self, request: AIRequest) -> AIResponse:
        if not self.enabled:
            return self._response(
                STATUS_DISABLED,
                task_type=request.task_type,
                model=self.model,
                fallback_reason="Provider is not enabled.",
            )

        if self._call_fn is not None:
            try:
                text = self._call_fn(request)
                return self._response(
                    OK, task_type=request.task_type, text=text, model=self.model
                )
            except Exception as exc:
                return self._response(
                    ERROR,
                    task_type=request.task_type,
                    model=self.model,
                    fallback_reason=f"Injected call failed: {exc}",
                )

        if self.requires_api_key and not self.api_key:
            return self._response(
                NOT_CONFIGURED,
                task_type=request.task_type,
                model=self.model,
                fallback_reason=(
                    f"No API key configured (set {self.api_key_env})."
                    if self.api_key_env
                    else "No API key configured."
                ),
            )
        if not self.requires_api_key and not self.base_url:
            return self._response(
                NOT_CONFIGURED,
                task_type=request.task_type,
                model=self.model,
                fallback_reason="No base URL configured.",
            )

        try:
            text = self._http_generate(request)
            return self._response(
                OK, task_type=request.task_type, text=text, model=self.model
            )
        except Exception as exc:
            return self._response(
                UNAVAILABLE,
                task_type=request.task_type,
                model=self.model,
                fallback_reason=f"Provider request failed: {exc}",
            )

    def _http_generate(self, request: AIRequest) -> str:  # pragma: no cover - network
        raise NotImplementedError(
            f"{self.provider_type} real HTTP path is not implemented; "
            "inject a call_fn or enable a configured provider."
        )


__all__ = [
    "AIProvider",
    "AIRequest",
    "AIResponse",
    "CallFn",
    "DisabledProvider",
    "HttpChatProvider",
    "ProviderHealth",
]
