from app.core.config import AppSettings
from app.model_layer.finbert_sentiment import FinbertSentimentService
from app.model_layer.model_schemas import DISABLED, OK
from app.model_layer.model_worker import ModelWorker


def test_worker_runs_in_fallback_mode_by_default() -> None:
    worker = ModelWorker(settings=AppSettings(models_enabled=False))
    assert worker.fallback_mode is True

    sentiment = worker.analyze_sentiment("text")
    assert sentiment.status == DISABLED
    assert sentiment.label == "NEUTRAL"

    text_result = worker.analyze_text("text")
    assert text_result.is_fallback is True

    kline = worker.score_klines([(1, 2, 3, 4)])
    assert kline.is_fallback is True

    embeddings = worker.embed(["a"])
    assert embeddings[0].is_fallback is True


def test_worker_status_reports_adapters() -> None:
    worker = ModelWorker(settings=AppSettings(models_enabled=False))
    status = worker.get_status()
    assert status["models_enabled"] is False
    assert status["fallback_mode"] is True
    assert status["any_model_available"] is False
    assert set(status["adapters"].keys()) == {"finbert", "fingpt", "kronos", "embeddings"}
    assert "finbert" in status["versions"]


def test_worker_uses_injected_available_adapter() -> None:
    finbert = FinbertSentimentService(
        inference_fn=lambda text: {"POSITIVE": 0.9, "NEGATIVE": 0.05, "NEUTRAL": 0.05}
    )
    worker = ModelWorker(settings=AppSettings(models_enabled=False), finbert=finbert)

    result = worker.analyze_sentiment("great quarter")
    assert result.status == OK
    assert result.label == "POSITIVE"

    status = worker.get_status()
    assert status["adapters"]["finbert"]["available"] is True
    assert status["any_model_available"] is True
