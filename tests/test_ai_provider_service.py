import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.ai_providers.ai_provider_models import AiProvider
from app.ai_providers.ai_provider_service import AiProviderService
from app.core.config import AppSettings
from app.database.base import Base


def create_test_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return engine, SessionLocal()


def test_seed_default_providers_is_idempotent() -> None:
    _, db = create_test_session()
    service = AiProviderService(settings=AppSettings())

    first = service.seed_default_providers(db)
    second = service.seed_default_providers(db)
    assert first == 9
    assert second == 0
    assert db.query(AiProvider).count() == 9


def test_default_active_is_disabled() -> None:
    _, db = create_test_session()
    service = AiProviderService(settings=AppSettings())
    assert service.get_active(db) == "DISABLED"
    assert service.get_fallback(db) == "DISABLED"


def test_set_active_and_fallback() -> None:
    _, db = create_test_session()
    service = AiProviderService(settings=AppSettings())

    service.set_active(db, "GEMINI")
    service.set_fallback(db, "MANUAL_PASTE")

    assert service.get_active(db) == "GEMINI"
    assert service.get_fallback(db) == "MANUAL_PASTE"

    active_rows = db.query(AiProvider).filter(AiProvider.is_active.is_(True)).all()
    assert len(active_rows) == 1
    assert active_rows[0].provider_key == "GEMINI"


def test_api_key_value_is_never_stored() -> None:
    _, db = create_test_session()
    service = AiProviderService(settings=AppSettings())
    providers = {p.provider_key: p for p in service.list_providers(db)}
    # Only the env var NAME is persisted, never a key value.
    assert providers["GEMINI"].api_key_env == "GEMINI_API_KEY"


def test_set_active_invalid_raises() -> None:
    _, db = create_test_session()
    service = AiProviderService(settings=AppSettings())
    with pytest.raises(ValueError):
        service.set_active(db, "NOT_A_PROVIDER")
