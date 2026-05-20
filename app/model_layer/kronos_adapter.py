"""Kronos K-line auxiliary-scoring adapter placeholder (Phase 16, step 16.4).

Provides an *auxiliary* score over OHLCV bars. Not yet wired to a real model:
by default returns a ``PLACEHOLDER`` fallback (score=None) so it never drives a
decision on its own. A caller/test may inject an ``inference_fn``.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from app.model_layer.model_schemas import ERROR, OK, PLACEHOLDER, KlineScoreResult

# inference_fn maps OHLCV bars -> {"score": float, "direction": str}
InferenceFn = Callable[[Sequence[Any]], dict[str, Any]]


class KronosAdapter:
    def __init__(
        self,
        model_name: str = "Kronos",
        model_version: str = "kronos_placeholder_v0",
        enabled: bool = False,
        inference_fn: InferenceFn | None = None,
    ) -> None:
        self.model_name = model_name
        self.model_version = model_version
        self.enabled = enabled
        self._inference_fn = inference_fn

    def is_available(self) -> bool:
        return self._inference_fn is not None

    def _placeholder(self) -> KlineScoreResult:
        return KlineScoreResult(
            score=None,
            direction=None,
            status=PLACEHOLDER,
            model_name=self.model_name,
            model_version=self.model_version,
            fallback_reason="Kronos adapter is a placeholder; no model wired.",
        )

    def score_klines(self, ohlcv: Sequence[Any]) -> KlineScoreResult:
        if self._inference_fn is None:
            return self._placeholder()
        try:
            payload = self._inference_fn(ohlcv)
            return KlineScoreResult(
                score=payload.get("score"),
                direction=payload.get("direction"),
                status=OK,
                model_name=self.model_name,
                model_version=self.model_version,
            )
        except Exception as exc:
            return KlineScoreResult(
                score=None,
                direction=None,
                status=ERROR,
                model_name=self.model_name,
                model_version=self.model_version,
                fallback_reason=f"Injected inference failed: {exc}",
            )


__all__ = ["KronosAdapter", "InferenceFn"]
