from collections.abc import Generator

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.main import app
from app.database.connection import get_db_session


def create_test_session_factory():
    engine = create_engine(
        "sqlite://",
        future=True,
        connect_args={
            "check_same_thread": False,
        },
        poolclass=StaticPool,
    )

    return sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
    )


def test_manual_option_routes_store_and_return_snapshot() -> None:
    session_factory = create_test_session_factory()

    def override_get_db_session() -> Generator[Session, None, None]:
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db_session] = override_get_db_session

    try:
        client = TestClient(app)

        response = client.post(
            "/api/options/manual-input",
            json={
                "raw_text": (
                    "AMD June 19 2026 170 call, stock around 165.20, "
                    "bid 8.20 ask 8.80, last 8.50, IV around 42.5%, "
                    "delta .48, gamma .025, theta -.09, vega .31, "
                    "volume 1200, OI 5400."
                ),
                "source_name": "Route Test",
            },
        )

        assert response.status_code == 200
        body = response.json()

        assert body["status"] == "OK"
        assert body["snapshot"]["symbol"] == "AMD"
        assert body["snapshot"]["option_type"] == "CALL"
        assert body["snapshot"]["strike"] == 170.0
        assert body["snapshot"]["mid_price"] == 8.5
        assert body["snapshot"]["source_name"] == "Route Test"

        list_response = client.get("/api/options/manual-snapshots?symbol=AMD")

        assert list_response.status_code == 200
        list_body = list_response.json()

        assert list_body["status"] == "OK"
        assert list_body["count"] == 1
        assert list_body["snapshots"][0]["symbol"] == "AMD"
    finally:
        app.dependency_overrides.clear()


def test_ticker_manual_option_route_uses_path_symbol() -> None:
    session_factory = create_test_session_factory()

    def override_get_db_session() -> Generator[Session, None, None]:
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db_session] = override_get_db_session

    try:
        client = TestClient(app)

        response = client.post(
            "/api/tickers/AMD/options/manual-input",
            json={
                "raw_text": "June 19 2026 170 call bid 8.20 ask 8.80",
            },
        )

        assert response.status_code == 200
        body = response.json()

        assert body["status"] == "OK"
        assert body["snapshot"]["symbol"] == "AMD"
        assert body["snapshot"]["option_type"] == "CALL"
        assert body["snapshot"]["strike"] == 170.0
    finally:
        app.dependency_overrides.clear()


def test_manual_option_analyze_route_returns_placeholder_analysis() -> None:
    session_factory = create_test_session_factory()

    def override_get_db_session() -> Generator[Session, None, None]:
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db_session] = override_get_db_session

    try:
        client = TestClient(app)

        route_debug_response = client.get("/api/options/manual-routes-debug")

        assert route_debug_response.status_code == 200

        create_response = client.post(
            "/api/options/manual-input",
            json={
                "raw_text": "AMD June 19 2026 170 call bid 8.20 ask 8.80",
            },
        )

        assert create_response.status_code == 200

        snapshot_id = create_response.json()["snapshot"]["id"]

        analyze_response = client.post(
            f"/api/options/manual-snapshots/{snapshot_id}/analyze"
        )

        assert analyze_response.status_code == 200
        body = analyze_response.json()

        assert body["status"] == "OK"
        assert body["snapshot"]["ai_status"] == "PLACEHOLDER_COMPLETE"
        assert body["snapshot"]["ai_analysis"] is not None
        assert "option_interpretation_label" in body["snapshot"]["ai_analysis"]
    finally:
        app.dependency_overrides.clear()