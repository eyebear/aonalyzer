"""FinBERT financial-sentiment adapter (Phase 16, step 16.2).

Heavy ``transformers`` import is lazy and wrapped in try/except, so importing
this module never requires the library. A test (or any caller) may inject an
``inference_fn`` to mock model output; when no model is available the adapter
returns a deterministic NEUTRAL fallback instead of raising.
"""

from __future__ import annotations

from collections.abc import Callable

from app.model_layer.model_schemas import (
    DISABLED,
    ERROR,
    MODEL_UNAVAILABLE,
    OK,
    SENTIMENT_NEGATIVE,
    SENTIMENT_NEUTRAL,
    SENTIMENT_POSITIVE,
    SentimentResult,
)

# inference_fn maps text -> {"POSITIVE": p, "NEGATIVE": p, "NEUTRAL": p}
InferenceFn = Callable[[str], dict[str, float]]

_LABEL_NORMALIZE = {
    "POSITIVE": SENTIMENT_POSITIVE,
    "POS": SENTIMENT_POSITIVE,
    "NEGATIVE": SENTIMENT_NEGATIVE,
    "NEG": SENTIMENT_NEGATIVE,
    "NEUTRAL": SENTIMENT_NEUTRAL,
}


class FinbertSentimentService:
    def __init__(
        self,
        model_name: str = "ProsusAI/finbert",
        model_version: str = "finbert_v1",
        enabled: bool = False,
        inference_fn: InferenceFn | None = None,
    ) -> None:
        self.model_name = model_name
        self.model_version = model_version
        self.enabled = enabled
        self._inference_fn = inference_fn
        self._pipeline = None

    def is_available(self) -> bool:
        if self._inference_fn is not None:
            return True
        if not self.enabled:
            return False
        return self._transformers_importable()

    def _transformers_importable(self) -> bool:
        try:
            import transformers  # noqa: F401
        except Exception:
            return False
        return True

    def _fallback(self, status: str, reason: str) -> SentimentResult:
        return SentimentResult(
            label=SENTIMENT_NEUTRAL,
            score=0.0,
            probabilities={},
            status=status,
            model_name=self.model_name,
            model_version=self.model_version,
            fallback_reason=reason,
        )

    def _result_from_probs(self, probs: dict[str, float]) -> SentimentResult:
        normalized = {
            _LABEL_NORMALIZE.get(str(k).upper(), str(k).upper()): float(v)
            for k, v in probs.items()
        }
        if not normalized:
            return self._fallback(ERROR, "Empty probability map from model.")
        label = max(normalized, key=lambda k: normalized[k])
        return SentimentResult(
            label=label,
            score=normalized[label],
            probabilities=normalized,
            status=OK,
            model_name=self.model_name,
            model_version=self.model_version,
        )

    def analyze(self, text: str) -> SentimentResult:
        if self._inference_fn is not None:
            try:
                return self._result_from_probs(self._inference_fn(text))
            except Exception as exc:
                return self._fallback(ERROR, f"Injected inference failed: {exc}")

        if not self.enabled:
            return self._fallback(DISABLED, "Models are disabled (fallback mode).")

        pipeline = self._load_pipeline()
        if pipeline is None:
            return self._fallback(
                MODEL_UNAVAILABLE, "transformers/FinBERT not available."
            )

        try:
            raw = pipeline(text, top_k=None)
            # transformers may return a list of {label, score} dicts.
            if isinstance(raw, list) and raw and isinstance(raw[0], list):
                raw = raw[0]
            probs = {item["label"]: item["score"] for item in raw}
            return self._result_from_probs(probs)
        except Exception as exc:
            return self._fallback(ERROR, f"FinBERT inference failed: {exc}")

    def _load_pipeline(self):
        if self._pipeline is not None:
            return self._pipeline
        try:
            from transformers import pipeline

            self._pipeline = pipeline("sentiment-analysis", model=self.model_name)
            return self._pipeline
        except Exception:
            return None


__all__ = ["FinbertSentimentService", "InferenceFn"]
