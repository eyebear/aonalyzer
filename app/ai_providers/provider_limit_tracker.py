"""In-memory provider usage / limit tracking (Phase 17, step 17.6).

Tracks per-provider call counts within the process and enforces optional
per-provider call limits (e.g. a free-tier daily cap). No limit configured means
unlimited. Persistence/quota windows are left for later phases.
"""

from __future__ import annotations

from typing import Any


class ProviderLimitTracker:
    def __init__(self, limits: dict[str, int] | None = None) -> None:
        self._limits = dict(limits or {})
        self._usage: dict[str, int] = {}

    def set_limit(self, provider_type: str, limit: int | None) -> None:
        if limit is None:
            self._limits.pop(provider_type, None)
        else:
            self._limits[provider_type] = limit

    def record(self, provider_type: str, count: int = 1) -> None:
        self._usage[provider_type] = self._usage.get(provider_type, 0) + count

    def usage(self, provider_type: str) -> int:
        return self._usage.get(provider_type, 0)

    def limit(self, provider_type: str) -> int | None:
        return self._limits.get(provider_type)

    def remaining(self, provider_type: str) -> int | None:
        limit = self._limits.get(provider_type)
        if limit is None:
            return None
        return max(0, limit - self.usage(provider_type))

    def is_over_limit(self, provider_type: str) -> bool:
        limit = self._limits.get(provider_type)
        if limit is None:
            return False
        return self.usage(provider_type) >= limit

    def reset(self, provider_type: str | None = None) -> None:
        if provider_type is None:
            self._usage.clear()
        else:
            self._usage.pop(provider_type, None)

    def snapshot(self) -> dict[str, dict[str, Any]]:
        keys = set(self._usage) | set(self._limits)
        return {
            ptype: {
                "usage": self.usage(ptype),
                "limit": self.limit(ptype),
                "remaining": self.remaining(ptype),
                "over_limit": self.is_over_limit(ptype),
            }
            for ptype in keys
        }


__all__ = ["ProviderLimitTracker"]
