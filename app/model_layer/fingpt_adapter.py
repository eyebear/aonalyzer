"""FinGPT financial-text adapter placeholder (Phase 16, step 16.3).

Not yet wired to a real model: by default returns a ``PLACEHOLDER`` fallback so
the system runs without it. A caller/test may inject an ``inference_fn`` to
supply structured output (summary + key points).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.model_layer.model_schemas import ERROR, OK, PLACEHOLDER, TextAnalysisResult

# inference_fn maps text -> {"summary": str, "key_points": list[str]}
InferenceFn = Callable[[str], dict[str, Any]]


class FinGptAdapter:
    def __init__(
        self,
        model_name: str = "FinGPT",
        model_version: str = "fingpt_placeholder_v0",
        enabled: bool = False,
        inference_fn: InferenceFn | None = None,
    ) -> None:
        self.model_name = model_name
        self.model_version = model_version
        self.enabled = enabled
        self._inference_fn = inference_fn

    def is_available(self) -> bool:
        # Placeholder: only "available" when explicitly mocked/injected.
        return self._inference_fn is not None

    def _placeholder(self) -> TextAnalysisResult:
        return TextAnalysisResult(
            summary=None,
            key_points=[],
            status=PLACEHOLDER,
            model_name=self.model_name,
            model_version=self.model_version,
            fallback_reason="FinGPT adapter is a placeholder; no model wired.",
        )

    def analyze_text(self, text: str) -> TextAnalysisResult:
        if self._inference_fn is None:
            return self._placeholder()
        try:
            payload = self._inference_fn(text)
            return TextAnalysisResult(
                summary=payload.get("summary"),
                key_points=list(payload.get("key_points", [])),
                status=OK,
                model_name=self.model_name,
                model_version=self.model_version,
            )
        except Exception as exc:
            return TextAnalysisResult(
                summary=None,
                key_points=[],
                status=ERROR,
                model_name=self.model_name,
                model_version=self.model_version,
                fallback_reason=f"Injected inference failed: {exc}",
            )


__all__ = ["FinGptAdapter", "InferenceFn"]
