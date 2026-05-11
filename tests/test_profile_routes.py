from fastapi.testclient import TestClient

from app.api.main import app

client = TestClient(app)


def test_get_active_profile_endpoint_returns_balanced_default() -> None:
    response = client.get("/api/settings/profile")

    assert response.status_code == 200

    body = response.json()

    assert body["active_profile_name"] == "Balanced Research Default"
    assert body["active_profile_version"] == "balanced_research_default_1.0"
    assert body["profile"]["profile_name"] == "Balanced Research Default"
    assert body["profile"]["option_dte_min"] == 45
    assert body["profile"]["option_dte_max"] == 90
    assert body["profile"]["hard_filters_can_be_bypassed"] is False


def test_list_profiles_endpoint_returns_initial_profiles() -> None:
    response = client.get("/api/settings/profiles")

    assert response.status_code == 200

    body = response.json()
    profile_names = {profile["profile_name"] for profile in body["profiles"]}

    assert "Balanced Research Default" in profile_names
    assert "Conservative Research" in profile_names
    assert "Aggressive Research" in profile_names
    assert "Custom" in profile_names


def test_save_custom_profile_rejects_hard_filter_bypass() -> None:
    active_profile_response = client.get("/api/settings/profile")
    payload = active_profile_response.json()["profile"]

    payload["profile_name"] = "Bad Custom"
    payload["profile_type"] = "CUSTOM"
    payload["profile_version"] = "bad_custom_1.0"
    payload["hard_filters_can_be_bypassed"] = True

    response = client.post("/api/settings/profile", json=payload)

    assert response.status_code == 422