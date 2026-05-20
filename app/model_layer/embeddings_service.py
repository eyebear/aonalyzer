"""Sentence-embeddings service (Phase 16, step 16.5).

Heavy ``sentence_transformers`` import is lazy and guarded, so importing this
module never requires it. A caller/test may inject an ``encode_fn`` to mock
vectors; with no model available the service returns empty fallback embeddings
rather than raising.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from app.model_layer.model_schemas import (
    DISABLED,
    ERROR,
    MODEL_UNAVAILABLE,
    OK,
    EmbeddingResult,
)

# encode_fn maps a list of texts -> a list of vectors.
EncodeFn = Callable[[Sequence[str]], Sequence[Sequence[float]]]


class EmbeddingsService:
    def __init__(
        self,
        model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
        model_version: str = "minilm_l6_v2",
        enabled: bool = False,
        encode_fn: EncodeFn | None = None,
    ) -> None:
        self.model_name = model_name
        self.model_version = model_version
        self.enabled = enabled
        self._encode_fn = encode_fn
        self._model = None

    def is_available(self) -> bool:
        if self._encode_fn is not None:
            return True
        if not self.enabled:
            return False
        return self._library_importable()

    def _library_importable(self) -> bool:
        try:
            import sentence_transformers  # noqa: F401
        except Exception:
            return False
        return True

    def _fallback(self, status: str, reason: str) -> EmbeddingResult:
        return EmbeddingResult(
            vector=[],
            dim=0,
            status=status,
            model_name=self.model_name,
            model_version=self.model_version,
            fallback_reason=reason,
        )

    def _ok(self, vector: Sequence[float]) -> EmbeddingResult:
        vec = [float(x) for x in vector]
        return EmbeddingResult(
            vector=vec,
            dim=len(vec),
            status=OK,
            model_name=self.model_name,
            model_version=self.model_version,
        )

    def embed(self, texts: Sequence[str]) -> list[EmbeddingResult]:
        if not texts:
            return []

        if self._encode_fn is not None:
            try:
                vectors = self._encode_fn(texts)
                return [self._ok(v) for v in vectors]
            except Exception as exc:
                return [self._fallback(ERROR, f"Injected encode failed: {exc}") for _ in texts]

        if not self.enabled:
            return [self._fallback(DISABLED, "Models are disabled (fallback mode).") for _ in texts]

        model = self._load_model()
        if model is None:
            return [
                self._fallback(MODEL_UNAVAILABLE, "sentence-transformers not available.")
                for _ in texts
            ]

        try:
            vectors = model.encode(list(texts))
            return [self._ok(list(v)) for v in vectors]
        except Exception as exc:
            return [self._fallback(ERROR, f"Embedding failed: {exc}") for _ in texts]

    def embed_one(self, text: str) -> EmbeddingResult:
        results = self.embed([text])
        return results[0] if results else self._fallback(ERROR, "No text to embed.")

    def _load_model(self):
        if self._model is not None:
            return self._model
        try:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name)
            return self._model
        except Exception:
            return None


__all__ = ["EmbeddingsService", "EncodeFn"]
