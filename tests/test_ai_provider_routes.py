from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.main import app
from app.database.base import Base
from app.database.connection import get_db_session

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def override_get_db_session() -> Generator[Session, None, None]:
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(autouse=True)
def reset_test_database():
    app.dependency_overrides.clear()
    app.dependency_overrides[get_db_session] = override_get_db_session
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    app.dependency_overrides.clear()


def test_list_providers_seeds_defaults() -> None:
    client = TestClient(app)
    response = client.get("/api/ai-providers")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 9
    assert body["active_provider"] == "DISABLED"


def test_set_active_provider() -> None:
    client = TestClient(app)
    response = client.post("/api/ai-providers/active", json={"provider_type": "GEMINI"})
    assert response.status_code == 200
    assert response.json()["active_provider"] == "GEMINI"

    listing = client.get("/api/ai-providers").json()
    assert listing["active_provider"] == "GEMINI"


def test_set_active_invalid_returns_400() -> None:
    client = TestClient(app)
    response = client.post("/api/ai-providers/active", json={"provider_type": "NOPE"})
    assert response.status_code == 400


def test_generate_default_is_disabled() -> None:
    client = TestClient(app)
    response = client.post(
        "/api/ai-providers/generate",
        json={"task_type": "GENERAL", "prompt": "hello"},
    )
    assert response.status_code == 200
    assert response.json()["response"]["status"] == "DISABLED"


def test_generate_manual_paste_after_selection() -> None:
    client = TestClient(app)
    client.post("/api/ai-providers/active", json={"provider_type": "MANUAL_PASTE"})

    response = client.post(
        "/api/ai-providers/generate",
        json={"task_type": "OPTION_TEXT_READER", "prompt": "AAPL 200C"},
    )
    body = response.json()["response"]
    assert body["status"] == "MANUAL_REQUIRED"
    assert body["manual_prompt"] == "AAPL 200C"


def test_status_endpoint() -> None:
    client = TestClient(app)
    response = client.get("/api/ai-providers/status")
    assert response.status_code == 200
    body = response.json()
    assert body["active_provider"] == "DISABLED"
    assert "providers" in body
