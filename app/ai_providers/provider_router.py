"""Provider routing by task type (Phase 17, step 17.4).

Pure ordering logic: given a task type, return the ordered list of provider
types to try (a per-task override or the active provider, then the fallback).
The manager resolves these to instances and handles availability.
"""

from __future__ import annotations


class ProviderRouter:
    def __init__(
        self,
        active_type: str,
        fallback_type: str,
        task_overrides: dict[str, str] | None = None,
    ) -> None:
        self.active_type = active_type
        self.fallback_type = fallback_type
        self.task_overrides = dict(task_overrides or {})

    def select(self, task_type: str) -> list[str]:
        ordered: list[str] = []
        primary = self.task_overrides.get(task_type, self.active_type)
        for candidate in [primary, self.fallback_type]:
            if candidate and candidate not in ordered:
                ordered.append(candidate)
        return ordered


__all__ = ["ProviderRouter"]
