"""Central AI provider access (Phase 17, step 17.2).

Resolves the active/fallback providers, routes a request by task type, enforces
usage limits, and always returns an ``AIResponse`` (never raises). With the
default config (active/fallback = DISABLED) every call returns a clean DISABLED
response, so the system runs without any external AI.
"""

from __future__ import annotations

from typing import Any

from app.ai_providers.provider_base import AIRequest, AIResponse, DisabledProvider
from app.ai_providers.provider_health_checker import ProviderHealthChecker
from app.ai_providers.provider_limit_tracker import ProviderLimitTracker
from app.ai_providers.provider_registry import ProviderRegistry, build_default_registry
from app.ai_providers.provider_router import ProviderRouter
from app.ai_providers.provider_types import (
    DISABLED,
    MANUAL_REQUIRED,
    OK,
    RATE_LIMITED,
    TASK_OPTION_TEXT_READER,
)
from app.core.config import get_settings

# Statuses that are acceptable terminal results (stop trying further providers).
_TERMINAL_STATUSES = frozenset({OK, MANUAL_REQUIRED})


class AIProviderManager:
    def __init__(
        self,
        settings: Any | None = None,
        *,
        registry: ProviderRegistry | None = None,
        router: ProviderRouter | None = None,
        health_checker: ProviderHealthChecker | None = None,
        limit_tracker: ProviderLimitTracker | None = None,
        active_type: str | None = None,
        fallback_type: str | None = None,
        task_overrides: dict[str, str] | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.registry = registry or build_default_registry(self.settings)
        self.active_type = active_type or self.settings.active_ai_provider
        self.fallback_type = fallback_type or self.settings.fallback_ai_provider
        self.router = router or ProviderRouter(
            self.active_type, self.fallback_type, task_overrides
        )
        self.health_checker = health_checker or ProviderHealthChecker()
        self.limit_tracker = limit_tracker or ProviderLimitTracker()

    def set_active(self, provider_type: str) -> None:
        self.active_type = provider_type
        self.router.active_type = provider_type

    def set_fallback(self, provider_type: str) -> None:
        self.fallback_type = provider_type
        self.router.fallback_type = provider_type

    def generate(
        self,
        task_type: str,
        prompt: str,
        *,
        system_prompt: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.2,
        metadata: dict[str, Any] | None = None,
    ) -> AIResponse:
        request = AIRequest(
            task_type=task_type,
            prompt=prompt,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            metadata=metadata or {},
        )

        last_response: AIResponse | None = None
        for provider_type in self.router.select(task_type):
            provider = self.registry.get(provider_type)

            if self.limit_tracker.is_over_limit(provider_type):
                last_response = AIResponse(
                    status=RATE_LIMITED,
                    provider_type=provider_type,
                    task_type=task_type,
                    fallback_reason="Provider usage limit reached.",
                )
                continue

            if not provider.is_available():
                last_response = provider.generate(request)
                continue

            self.limit_tracker.record(provider_type)
            response = provider.generate(request)
            if response.status in _TERMINAL_STATUSES:
                return response
            last_response = response

        if last_response is not None:
            return last_response
        return DisabledProvider().generate(request)

    def read_option_text(self, option_text: str, *, system_prompt: str | None = None) -> AIResponse:
        """Convenience for the OPTION_TEXT_READER task (step 17.15)."""
        return self.generate(
            TASK_OPTION_TEXT_READER,
            option_text,
            system_prompt=system_prompt,
        )

    def get_status(self) -> dict[str, Any]:
        return {
            "active_provider": self.active_type,
            "fallback_provider": self.fallback_type,
            "ai_enabled": self.active_type != DISABLED,
            "providers": self.registry.statuses(),
            "health": self.health_checker.check_all(self.registry),
            "limits": self.limit_tracker.snapshot(),
        }


__all__ = ["AIProviderManager"]
