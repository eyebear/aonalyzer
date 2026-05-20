from fastapi.testclient import TestClient

from app.api.main import app

client = TestClient(app)


def test_model_status_endpoint() -> None:
    response = client.get("/api/models/status")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "OK"
    assert body["models_enabled"] is False
    assert body["fallback_mode"] is True
    assert set(body["adapters"].keys()) == {"finbert", "fingpt", "kronos", "embeddings"}


def test_model_versions_endpoint() -> None:
    response = client.get("/api/models/versions")
    assert response.status_code == 200
    body = response.json()
    assert "finbert" in body["versions"]
    assert body["versions"]["finbert"]["model_type"] == "SENTIMENT"


def test_model_sentiment_endpoint_fallback() -> None:
    response = client.post("/api/models/sentiment", json={"text": "Earnings beat estimates"})
    assert response.status_code == 200
    body = response.json()
    result = body["result"]
    # Models disabled by default -> deterministic NEUTRAL fallback, no model load.
    assert result["status"] == "DISABLED"
    assert result["label"] == "NEUTRAL"
    assert result["is_fallback"] is True
