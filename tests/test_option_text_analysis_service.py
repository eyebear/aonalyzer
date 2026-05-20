from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.ai_analysis.option_text_analysis_service import OptionTextAnalysisService
from app.ai_providers.gemini_provider import GeminiProvider
from app.ai_providers.provider_base import DisabledProvider
from app.ai_providers.provider_manager import AIProviderManager
from app.ai_providers.provider_registry import ProviderRegistry
from app.ai_providers.provider_types import DISABLED, GEMINI
from app.core.config import AppSettings
from app.database.base import Base
from app.options.manual_option_input_service import ManualOptionInputService

VALID_OPTION_JSON = (
    '{"plain_english_summary": "A long-dated AAPL call.", '
    '"option_interpretation_label": "OPTION_TEXT_PARSED_NEEDS_REVIEW", '
    '"missing_fields": [], "iv_comment": "IV detected"}'
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


def _create_snapshot(db) -> int:
    record = ManualOptionInputService().create_manual_snapshot(
        db=db,
        raw_text="AAPL 200 CALL exp 2026-07-15 bid 4.90 ask 5.10 IV 50%",
        symbol="AAPL",
    )
    return record.id


def test_fallback_produces_ten_field_explanation() -> None:
    _, db = create_test_session()
    snapshot_id = _create_snapshot(db)

    service = OptionTextAnalysisService(settings=AppSettings())  # AI disabled
    result = service.analyze_snapshot(db, snapshot_id)

    assert result.status == "FALLBACK"
    assert result.is_fallback is True
    assert result.plain_english_summary  # non-empty
    assert len(result.to_payload()) == 10

    stored = service.get_stored_analysis(db, snapshot_id)
    assert stored["ai_status"] == "FALLBACK"
    assert stored["ai_summary"] == result.plain_english_summary


def test_ai_path_with_valid_option_json() -> None:
    _, db = create_test_session()
    snapshot_id = _create_snapshot(db)

    service = OptionTextAnalysisService(
        settings=AppSettings(), provider_manager=_manager_returning(VALID_OPTION_JSON)
    )
    result = service.analyze_snapshot(db, snapshot_id)

    assert result.status == "AI_OK"
    assert result.is_fallback is False
    assert result.plain_english_summary == "A long-dated AAPL call."
    assert result.iv_comment == "IV detected"

    stored = service.get_stored_analysis(db, snapshot_id)
    assert stored["ai_status"] == "AI_OK"


def test_invalid_option_json_falls_back() -> None:
    _, db = create_test_session()
    snapshot_id = _create_snapshot(db)

    service = OptionTextAnalysisService(
        settings=AppSettings(), provider_manager=_manager_returning("garbage, not json")
    )
    result = service.analyze_snapshot(db, snapshot_id)
    assert result.status == "FALLBACK"


def test_missing_snapshot_raises() -> None:
    _, db = create_test_session()
    service = OptionTextAnalysisService(settings=AppSettings())
    try:
        service.analyze_snapshot(db, 999)
        raise AssertionError("expected ValueError")
    except ValueError:
        pass
