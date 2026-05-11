from fastapi.testclient import TestClient

from app.api.main import app

client = TestClient(app)


def test_health_check_returns_ok() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()

    assert body["status"] == "ok"
    assert body["app_name"] == "Ao Ao Analyzer"
    assert body["technical_name"] == "aoaoanalyzer"


def test_system_status_returns_local_infrastructure_settings() -> None:
    response = client.get("/api/system/status")

    assert response.status_code == 200
    body = response.json()

    assert body["status"] == "starting"
    assert body["app_name"] == "Ao Ao Analyzer"
    assert body["technical_name"] == "aoaoanalyzer"
    assert body["default_strategy_profile"] == "Balanced Research Default"
    assert "postgres_host" in body
    assert "redis_host" in body