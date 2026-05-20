from app.model_layer.embeddings_service import EmbeddingsService
from app.model_layer.finbert_sentiment import FinbertSentimentService
from app.model_layer.fingpt_adapter import FinGptAdapter
from app.model_layer.kronos_adapter import KronosAdapter
from app.model_layer.model_schemas import (
    DISABLED,
    MODEL_UNAVAILABLE,
    OK,
    PLACEHOLDER,
    SENTIMENT_POSITIVE,
)


# ---- FinBERT sentiment ----
def test_finbert_injected_inference_returns_ok() -> None:
    service = FinbertSentimentService(
        enabled=False,
        inference_fn=lambda text: {"POSITIVE": 0.7, "NEGATIVE": 0.1, "NEUTRAL": 0.2},
    )
    assert service.is_available() is True
    result = service.analyze("Company beats earnings")
    assert result.status == OK
    assert result.label == SENTIMENT_POSITIVE
    assert result.score == 0.7
    assert result.is_fallback is False


def test_finbert_disabled_returns_neutral_fallback() -> None:
    service = FinbertSentimentService(enabled=False)
    assert service.is_available() is False
    result = service.analyze("anything")
    assert result.status == DISABLED
    assert result.label == "NEUTRAL"
    assert result.is_fallback is True


def test_finbert_enabled_but_library_missing_is_unavailable() -> None:
    # transformers is not installed in CI -> graceful MODEL_UNAVAILABLE, no raise.
    service = FinbertSentimentService(enabled=True)
    result = service.analyze("anything")
    assert result.status == MODEL_UNAVAILABLE
    assert result.label == "NEUTRAL"


# ---- FinGPT placeholder ----
def test_fingpt_placeholder_by_default() -> None:
    adapter = FinGptAdapter(enabled=True)
    assert adapter.is_available() is False
    result = adapter.analyze_text("some filing text")
    assert result.status == PLACEHOLDER
    assert result.summary is None


def test_fingpt_injected_inference() -> None:
    adapter = FinGptAdapter(
        inference_fn=lambda text: {"summary": "bullish", "key_points": ["growth"]}
    )
    result = adapter.analyze_text("text")
    assert result.status == OK
    assert result.summary == "bullish"
    assert result.key_points == ["growth"]


# ---- Kronos placeholder ----
def test_kronos_placeholder_by_default() -> None:
    adapter = KronosAdapter(enabled=True)
    assert adapter.is_available() is False
    result = adapter.score_klines([(1, 2, 3, 4)])
    assert result.status == PLACEHOLDER
    assert result.score is None


def test_kronos_injected_inference() -> None:
    adapter = KronosAdapter(
        inference_fn=lambda bars: {"score": 0.8, "direction": "UP"}
    )
    result = adapter.score_klines([(1, 2, 3, 4)])
    assert result.status == OK
    assert result.score == 0.8
    assert result.direction == "UP"


# ---- Embeddings ----
def test_embeddings_injected_encode() -> None:
    service = EmbeddingsService(
        encode_fn=lambda texts: [[0.1, 0.2, 0.3] for _ in texts]
    )
    results = service.embed(["a", "b"])
    assert len(results) == 2
    assert results[0].status == OK
    assert results[0].dim == 3
    assert results[0].vector == [0.1, 0.2, 0.3]


def test_embeddings_disabled_returns_fallback() -> None:
    service = EmbeddingsService(enabled=False)
    result = service.embed_one("text")
    assert result.status == DISABLED
    assert result.vector == []
    assert result.is_fallback is True


def test_embeddings_empty_input() -> None:
    service = EmbeddingsService(encode_fn=lambda texts: [])
    assert service.embed([]) == []
