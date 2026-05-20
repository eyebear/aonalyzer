"""Model worker foundation (Phase 16, steps 16.1, 16.8).

Single entry point for pretrained-model inference. It owns the adapters and
guarantees that every call returns a schema object (never raises): when models
are disabled or unavailable, adapters return fallback output, so the rest of the
system runs unchanged in fallback mode. Adapters are injectable for tests.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from app.core.config import AppSettings, get_settings
from app.model_layer.embeddings_service import EmbeddingsService
from app.model_layer.finbert_sentiment import FinbertSentimentService
from app.model_layer.fingpt_adapter import FinGptAdapter
from app.model_layer.kronos_adapter import KronosAdapter
from app.model_layer.model_schemas import (
    EmbeddingResult,
    KlineScoreResult,
    SentimentResult,
    TextAnalysisResult,
)
from app.model_layer.model_version_registry import (
    ModelVersionRegistry,
    model_version_registry,
)


def _version_for(registry: ModelVersionRegistry, key: str, default: str) -> str:
    version = registry.get(key)
    return version.version if version is not None else default


class ModelWorker:
    def __init__(
        self,
        settings: AppSettings | None = None,
        *,
        registry: ModelVersionRegistry | None = None,
        finbert: FinbertSentimentService | None = None,
        fingpt: FinGptAdapter | None = None,
        kronos: KronosAdapter | None = None,
        embeddings: EmbeddingsService | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.registry = registry or model_version_registry
        enabled = self.settings.models_enabled

        self.finbert = finbert or FinbertSentimentService(
            model_name=self.settings.finbert_model_name,
            model_version=_version_for(self.registry, "finbert", "finbert_v1"),
            enabled=enabled,
        )
        self.fingpt = fingpt or FinGptAdapter(
            model_name=self.settings.fingpt_model_name,
            model_version=_version_for(self.registry, "fingpt", "fingpt_placeholder_v0"),
            enabled=enabled,
        )
        self.kronos = kronos or KronosAdapter(
            model_name=self.settings.kronos_model_name,
            model_version=_version_for(self.registry, "kronos", "kronos_placeholder_v0"),
            enabled=enabled,
        )
        self.embeddings = embeddings or EmbeddingsService(
            model_name=self.settings.embeddings_model_name,
            model_version=_version_for(self.registry, "embeddings", "minilm_l6_v2"),
            enabled=enabled,
        )

    # ---- inference (each returns a schema object, never raises) ----
    def analyze_sentiment(self, text: str) -> SentimentResult:
        return self.finbert.analyze(text)

    def analyze_text(self, text: str) -> TextAnalysisResult:
        return self.fingpt.analyze_text(text)

    def score_klines(self, ohlcv: Sequence[Any]) -> KlineScoreResult:
        return self.kronos.score_klines(ohlcv)

    def embed(self, texts: Sequence[str]) -> list[EmbeddingResult]:
        return self.embeddings.embed(texts)

    def embed_one(self, text: str) -> EmbeddingResult:
        return self.embeddings.embed_one(text)

    # ---- introspection ----
    @property
    def fallback_mode(self) -> bool:
        """True when no real model is in play (master switch off)."""
        return not self.settings.models_enabled

    def get_status(self) -> dict[str, Any]:
        adapters = {
            "finbert": {
                "available": self.finbert.is_available(),
                "model_name": self.finbert.model_name,
                "model_version": self.finbert.model_version,
                "type": "SENTIMENT",
            },
            "fingpt": {
                "available": self.fingpt.is_available(),
                "model_name": self.fingpt.model_name,
                "model_version": self.fingpt.model_version,
                "type": "TEXT (placeholder)",
            },
            "kronos": {
                "available": self.kronos.is_available(),
                "model_name": self.kronos.model_name,
                "model_version": self.kronos.model_version,
                "type": "KLINE (placeholder)",
            },
            "embeddings": {
                "available": self.embeddings.is_available(),
                "model_name": self.embeddings.model_name,
                "model_version": self.embeddings.model_version,
                "type": "EMBEDDING",
            },
        }
        return {
            "models_enabled": self.settings.models_enabled,
            "fallback_mode": self.fallback_mode,
            "any_model_available": any(a["available"] for a in adapters.values()),
            "adapters": adapters,
            "versions": self.registry.to_dict(),
        }


__all__ = ["ModelWorker"]
