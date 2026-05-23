"""Phase 42, step 42.3 — embedding service for memory.

Wraps the Phase 16 ``EmbeddingsService`` (sentence-transformers) and falls back
to a deterministic, dependency-free hash embedding when no model is available.
The fallback is reproducible so vector search behaves identically offline and
in tests — it is supporting context only, never a source of invented values.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Sequence

from app.model_layer.embeddings_service import EmbeddingsService

FALLBACK_DIM = 64
_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall((text or "").lower())


def deterministic_embedding(text: str, dim: int = FALLBACK_DIM) -> list[float]:
    """A reproducible bag-of-hashed-tokens embedding, L2-normalized."""
    vec = [0.0] * dim
    for token in _tokenize(text):
        h = int(hashlib.sha1(token.encode("utf-8")).hexdigest(), 16)
        idx = h % dim
        sign = 1.0 if (h >> 8) % 2 == 0 else -1.0
        vec[idx] += sign
    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0:
        return vec
    return [x / norm for x in vec]


class MemoryEmbeddingService:
    def __init__(self, embeddings_service: EmbeddingsService | None = None) -> None:
        self.embeddings_service = embeddings_service or EmbeddingsService()

    def embed_text(self, text: str) -> tuple[list[float], str]:
        """Return (vector, model_name). Uses the real model when available."""
        if self.embeddings_service.is_available():
            result = self.embeddings_service.embed_one(text)
            if result.vector:
                return list(result.vector), result.model_name
        return deterministic_embedding(text), "deterministic_hash_fallback"

    def embed_many(self, texts: Sequence[str]) -> list[tuple[list[float], str]]:
        return [self.embed_text(t) for t in texts]


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


__all__ = [
    "FALLBACK_DIM",
    "MemoryEmbeddingService",
    "cosine_similarity",
    "deterministic_embedding",
]
