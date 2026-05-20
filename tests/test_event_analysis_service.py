from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.ai_analysis.event_analysis_models import EventAnalysis
from app.ai_analysis.event_analysis_service import EventAnalysisService
from app.ai_providers.gemini_provider import GeminiProvider
from app.ai_providers.provider_base import DisabledProvider
from app.ai_providers.provider_manager import AIProviderManager
from app.ai_providers.provider_registry import ProviderRegistry
from app.ai_providers.provider_types import DISABLED, GEMINI
from app.core.config import AppSettings
from app.database.base import Base
from app.database.models import Event

VALID_JSON = (
    '{"summary": "Strong beat", "sentiment": "POSITIVE", '
    '"price_impact": "NOT_PRICED_IN", "key_points": ["beat EPS"], '
    '"risk_flags": [], "affected_symbols": ["AAPL"], "confidence": "HIGH"}'
)


def create_test_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return engine, SessionLocal()


def _manager_returning(text: str) -> AIProviderManager:
    gemini = GeminiProvider(enabled=True, api_key="k", call_fn=lambda r: text)
    registry = ProviderRegistry({DISABLED: DisabledProvider(), GEMINI: gemini})
    return AIProviderManager(
        settings=AppSettings(), registry=registry, active_type=GEMINI, fallback_type=DISABLED
    )


def _seed_event(db, *, importance="HIGH", symbol="AAPL", headline="Co beats earnings") -> int:
    event = Event(
        source="news",
        event_type="NEWS",
        importance_level=importance,
        headline=headline,
        symbol=symbol,
        detected_time=datetime.now(timezone.utc),
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event.id


def test_fallback_when_ai_disabled() -> None:
    _, db = create_test_session()
    event_id = _seed_event(db)

    service = EventAnalysisService(settings=AppSettings())  # active DISABLED
    row = service.analyze_event(db, event_id)

    assert row.is_fallback is True
    assert row.analysis_status == "FALLBACK"
    assert "Co beats earnings" in row.summary
    assert db.query(EventAnalysis).count() == 1


def test_ai_path_with_valid_json() -> None:
    _, db = create_test_session()
    event_id = _seed_event(db)

    service = EventAnalysisService(
        settings=AppSettings(), provider_manager=_manager_returning(VALID_JSON)
    )
    row = service.analyze_event(db, event_id)

    assert row.analysis_status == "AI_OK"
    assert row.is_fallback is False
    assert row.sentiment == "POSITIVE"
    assert row.price_impact == "NOT_PRICED_IN"
    assert row.key_points_json == ["beat EPS"]


def test_invalid_ai_json_falls_back() -> None:
    _, db = create_test_session()
    event_id = _seed_event(db)

    service = EventAnalysisService(
        settings=AppSettings(), provider_manager=_manager_returning("not json at all")
    )
    row = service.analyze_event(db, event_id)
    assert row.analysis_status == "FALLBACK"
    assert "parseable" in (row.fallback_reason or "")


def test_analyze_event_is_idempotent() -> None:
    _, db = create_test_session()
    event_id = _seed_event(db)
    service = EventAnalysisService(settings=AppSettings())
    service.analyze_event(db, event_id)
    service.analyze_event(db, event_id)
    assert db.query(EventAnalysis).count() == 1


def test_high_importance_filter() -> None:
    _, db = create_test_session()
    _seed_event(db, importance="HIGH", headline="High one")
    _seed_event(db, importance="LOW", headline="Low one")

    service = EventAnalysisService(settings=AppSettings())  # min HIGH
    summary = service.analyze_high_importance(db, limit=10)

    assert summary["analyzed"] == 1
    assert summary["skipped_low_importance"] == 1
    assert db.query(EventAnalysis).count() == 1


def test_missing_event_raises() -> None:
    _, db = create_test_session()
    service = EventAnalysisService(settings=AppSettings())
    try:
        service.analyze_event(db, 999)
        raise AssertionError("expected ValueError")
    except ValueError:
        pass
