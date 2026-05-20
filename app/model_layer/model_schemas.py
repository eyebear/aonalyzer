"""Consistent output schemas for the pretrained model layer (Phase 16, step 16.7).

Every adapter returns one of these dataclasses with an explicit ``status`` so the
rest of the system can treat a real model output and a fallback output uniformly.
No heavy ML imports here -- these are plain dataclasses.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Model output statuses.
OK = "OK"  # produced by a real model
DISABLED = "DISABLED"  # models globally/locally disabled -> deterministic fallback
MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"  # enabled but library/weights not loadable
PLACEHOLDER = "PLACEHOLDER"  # adapter is a not-yet-implemented placeholder
ERROR = "ERROR"  # model raised at inference time -> fallback returned

# Statuses that mean "this did not come from a real model" (i.e. fallback).
FALLBACK_STATUSES = frozenset({DISABLED, MODEL_UNAVAILABLE, PLACEHOLDER, ERROR})

# Sentiment labels.
SENTIMENT_POSITIVE = "POSITIVE"
SENTIMENT_NEGATIVE = "NEGATIVE"
SENTIMENT_NEUTRAL = "NEUTRAL"


@dataclass(frozen=True)
class SentimentResult:
    label: str
    score: float
    probabilities: dict[str, float] = field(default_factory=dict)
    status: str = OK
    model_name: str | None = None
    model_version: str | None = None
    fallback_reason: str | None = None

    @property
    def is_fallback(self) -> bool:
        return self.status in FALLBACK_STATUSES

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "score": self.score,
            "probabilities": dict(self.probabilities),
            "status": self.status,
            "model_name": self.model_name,
            "model_version": self.model_version,
            "fallback_reason": self.fallback_reason,
            "is_fallback": self.is_fallback,
        }


@dataclass(frozen=True)
class TextAnalysisResult:
    summary: str | None
    key_points: list[str] = field(default_factory=list)
    status: str = OK
    model_name: str | None = None
    model_version: str | None = None
    fallback_reason: str | None = None

    @property
    def is_fallback(self) -> bool:
        return self.status in FALLBACK_STATUSES

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "key_points": list(self.key_points),
            "status": self.status,
            "model_name": self.model_name,
            "model_version": self.model_version,
            "fallback_reason": self.fallback_reason,
            "is_fallback": self.is_fallback,
        }


@dataclass(frozen=True)
class KlineScoreResult:
    score: float | None
    direction: str | None
    status: str = OK
    model_name: str | None = None
    model_version: str | None = None
    fallback_reason: str | None = None

    @property
    def is_fallback(self) -> bool:
        return self.status in FALLBACK_STATUSES

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "direction": self.direction,
            "status": self.status,
            "model_name": self.model_name,
            "model_version": self.model_version,
            "fallback_reason": self.fallback_reason,
            "is_fallback": self.is_fallback,
        }


@dataclass(frozen=True)
class EmbeddingResult:
    vector: list[float] = field(default_factory=list)
    dim: int = 0
    status: str = OK
    model_name: str | None = None
    model_version: str | None = None
    fallback_reason: str | None = None

    @property
    def is_fallback(self) -> bool:
        return self.status in FALLBACK_STATUSES

    def to_dict(self) -> dict[str, Any]:
        return {
            "vector": list(self.vector),
            "dim": self.dim,
            "status": self.status,
            "model_name": self.model_name,
            "model_version": self.model_version,
            "fallback_reason": self.fallback_reason,
            "is_fallback": self.is_fallback,
        }


__all__ = [
    "DISABLED",
    "ERROR",
    "FALLBACK_STATUSES",
    "MODEL_UNAVAILABLE",
    "OK",
    "PLACEHOLDER",
    "SENTIMENT_NEGATIVE",
    "SENTIMENT_NEUTRAL",
    "SENTIMENT_POSITIVE",
    "EmbeddingResult",
    "KlineScoreResult",
    "SentimentResult",
    "TextAnalysisResult",
]
