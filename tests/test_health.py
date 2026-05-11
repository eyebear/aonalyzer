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


def test_system_status_declares_research_only_boundary() -> None:
    response = client.get("/api/system/status")

    assert response.status_code == 200
    body = response.json()

    assert body["research_only"] is True
    assert body["broker_connected"] is False
    assert body["auto_trading_enabled"] is False
    assert body["default_strategy_profile"] == "Balanced Research Default"