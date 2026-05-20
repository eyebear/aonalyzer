"""Provider health checking (Phase 17, step 17.5)."""

from __future__ import annotations

from typing import Any

from app.ai_providers.provider_base import AIProvider, ProviderHealth
from app.ai_providers.provider_registry import ProviderRegistry


class ProviderHealthChecker:
    def check(self, provider: AIProvider) -> ProviderHealth:
        try:
            return provider.health_check()
        except Exception as exc:
            return ProviderHealth(
                provider_type=getattr(provider, "provider_type", "UNKNOWN"),
                healthy=False,
                status="ERROR",
                detail=f"Health check raised: {exc}",
            )

    def check_all(self, registry: ProviderRegistry) -> dict[str, dict[str, Any]]:
        results: dict[str, dict[str, Any]] = {}
        for ptype in registry.list_types():
            results[ptype] = self.check(registry.get(ptype)).to_dict()
        return results


__all__ = ["ProviderHealthChecker"]
