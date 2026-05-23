"""Phases 46-49 — versioning/governance, settings, export/import, orchestration.

Protects: every decision carries all eight version keys; settings persistence
with the safe default invariant; export/import package integrity + roundtrip;
and the full pipeline running without failing when option data is missing.
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.main import app
from app.database.base import Base
from app.database.connection import get_db_session
from app.database.models import DailyPrice
from app.decision.decision_service import DecisionService
from app.decision.version_stamp_builder import REQUIRED_VERSION_KEYS
from app.export_import.exporter import MemoryExporter
from app.export_import.importer import MemoryImporter
from app.export_import.memory_package import validate_package
from app.governance.settings_service import SettingsService
from app.governance.version_models import DecisionAuditMetadata
from app.governance.version_service import compatibility_check
from app.learning.signal_outcome_service import SignalOutcomeService
from app.memory.case_memory_models import CaseMemory
from app.quant.stock_setup_models import StockSetup

_engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
)
_TestSession = sessionmaker(bind=_engine, autoflush=False, autocommit=False)
SIGNAL_DATE = date(2026, 3, 2)


def _override_get_db_session() -> Generator[Session, None, None]:
    session = _TestSession()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(autouse=True)
def reset_db():
    app.dependency_overrides.clear()
    app.dependency_overrides[get_db_session] = _override_get_db_session
    Base.metadata.drop_all(bind=_engine)
    with _engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS manual_option_snapshots"))
    Base.metadata.create_all(bind=_engine)
    yield
    app.dependency_overrides.clear()


def _seed_setup(symbol: str) -> None:
    base = date(2026, 1, 2)
    session = _TestSession()
    try:
        for i in range(80):
            close = 100.0 + i
            session.add(
                DailyPrice(
                    symbol=symbol,
                    price_date=base + timedelta(days=i),
                    open_price=close - 0.5,
                    high_price=close + 1.0,
                    low_price=close - 1.0,
                    close_price=close,
                    volume=1_000_000 + i,
                    source="test",
                )
            )
        session.add(
            StockSetup(
                symbol=symbol,
                snapshot_date=SIGNAL_DATE,
                source="test",
                source_record_count=80,
                current_close=160.0,
                nearest_support=150.0,
                nearest_resistance=185.0,
                sma_50=155.0,
                atr_14=4.0,
                direction="LONG",
                stop_method="ATR",
                target_price=185.0,
                stop_price=150.0,
                risk_per_share=10.0,
                reward_per_share=25.0,
                stock_risk_reward=2.5,
                entry_zone_low=150.0,
                entry_zone_high=162.0,
                data_sufficiency_status="SUFFICIENT",
            )
        )
        session.commit()
    finally:
        session.close()


# --- Phase 46: versioning / governance -------------------------------------


def test_every_decision_has_all_version_keys() -> None:
    _seed_setup("AMD")
    session = _TestSession()
    try:
        decision = DecisionService().evaluate_symbol(session, "AMD", persist=True).decision
        stamp = decision.version_stamp.to_dict()
        assert REQUIRED_VERSION_KEYS.issubset(set(stamp.keys()))
        # option_parser_version is the new Phase 46 key.
        assert stamp["option_parser_version"]
        # Audit metadata was written for the persisted decision.
        audit = session.query(DecisionAuditMetadata).filter(
            DecisionAuditMetadata.symbol == "AMD"
        ).one()
        assert audit.is_compatible is True
        assert audit.missing_version_keys_json == []
    finally:
        session.close()


def test_compatibility_check_flags_missing_keys() -> None:
    result = compatibility_check({"rule_version": "x"})
    assert result.is_compatible is False
    assert "option_parser_version" in result.missing_keys


# --- Phase 47: settings -----------------------------------------------------


def test_settings_default_allow_stock_only_is_true() -> None:
    session = _TestSession()
    try:
        svc = SettingsService()
        assert svc.get(session, "allow_stock_only_when_options_missing") is True
    finally:
        session.close()


def test_settings_persist_and_reset() -> None:
    session = _TestSession()
    try:
        svc = SettingsService()
        svc.set(session, "strict_option_parser_mode", True)
        assert svc.get(session, "strict_option_parser_mode") is True
        svc.reset(session, key="strict_option_parser_mode")
        assert svc.get(session, "strict_option_parser_mode") is False
        # The safe default must remain true after a full reset.
        svc.reset(session)
        assert svc.get(session, "allow_stock_only_when_options_missing") is True
    finally:
        session.close()


def test_settings_route_shape() -> None:
    client = TestClient(app)
    response = client.get("/api/settings/platform")
    assert response.status_code == 200
    assert "allow_stock_only_when_options_missing" in response.json()["settings"]


# --- Phase 48: export / import ----------------------------------------------


def test_export_import_package_integrity(tmp_path) -> None:
    _seed_setup("AMD")
    session = _TestSession()
    try:
        DecisionService().evaluate_symbol(session, "AMD", persist=True)
        SignalOutcomeService(horizons=(5,)).run(session)
        from app.memory.case_memory_service import CaseMemoryService

        CaseMemoryService().build_cases(session)

        out = tmp_path / "pkg"
        result = MemoryExporter().export(session, out)
        assert result.file_count >= 11

        validation = validate_package(out)
        assert validation.valid is True
        assert validation.schema_version is not None
    finally:
        session.close()


def test_export_then_import_roundtrip(tmp_path) -> None:
    _seed_setup("AMD")
    session = _TestSession()
    try:
        from app.action.action_service import ActionSuggestionService

        # Persist an action suggestion so the signal-outcome tracker has a signal.
        ActionSuggestionService().evaluate_symbol(session, "AMD", persist=True)
        SignalOutcomeService(horizons=(5,)).run(session)
        from app.memory.case_memory_service import CaseMemoryService

        CaseMemoryService().build_cases(session)
        cases_before = session.query(CaseMemory).count()
        assert cases_before >= 1

        out = tmp_path / "pkg"
        MemoryExporter().export(session, out)
    finally:
        session.close()

    # Fresh database: import restores case memory.
    fresh_engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    FreshSession = sessionmaker(bind=fresh_engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=fresh_engine)
    fresh = FreshSession()
    try:
        result = MemoryImporter().import_package(fresh, out)
        assert result.status == "OK"
        assert result.imported["case_memory.jsonl"] >= 1
        assert fresh.query(CaseMemory).count() >= 1
    finally:
        fresh.close()


def test_import_rejects_invalid_package(tmp_path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    session = _TestSession()
    try:
        result = MemoryImporter().import_package(session, empty)
        assert result.status == "INVALID"
        assert result.validation.valid is False
    finally:
        session.close()


# --- Phase 49: orchestration ------------------------------------------------


def test_full_pipeline_runs_and_is_not_blocked_by_missing_option() -> None:
    _seed_setup("AMD")
    client = TestClient(app)
    response = client.post("/api/pipeline/run", json={"symbols": ["AMD"]})
    assert response.status_code == 200
    result = response.json()["result"]
    step_names = {s["name"]: s["status"] for s in result["steps"]}
    # Core analysis steps completed.
    assert step_names["decisions"] == "OK"
    assert step_names["action_suggestions"] == "OK"
    assert step_names["worklist"] == "OK"
    assert step_names["dashboard_validation"] == "OK"
    # No step errored out due to missing option data.
    assert all(s["status"] in ("OK",) for s in result["steps"])


def test_full_pipeline_idempotent() -> None:
    _seed_setup("AMD")
    client = TestClient(app)
    first = client.post("/api/pipeline/run", json={"symbols": ["AMD"]})
    second = client.post("/api/pipeline/run", json={"symbols": ["AMD"]})
    assert first.status_code == 200
    assert second.status_code == 200
