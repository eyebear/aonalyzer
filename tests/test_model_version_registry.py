from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.database.base import Base
from app.model_layer.model_version_registry import (
    ModelVersion,
    ModelVersionRegistry,
    model_version_registry,
)


def create_test_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return engine, SessionLocal()


def test_default_registry_contains_known_models() -> None:
    keys = {v.key for v in model_version_registry.list_versions()}
    assert {"finbert", "fingpt", "kronos", "embeddings"} <= keys


def test_register_and_get() -> None:
    registry = ModelVersionRegistry(versions=[])
    registry.register(ModelVersion("x", "X", "x_v1", "SENTIMENT"))
    assert registry.get("x").version == "x_v1"
    assert registry.get("missing") is None


def test_persist_to_db_is_idempotent() -> None:
    _, db = create_test_session()
    registry = ModelVersionRegistry()

    first = registry.persist_to_db(db)
    second = registry.persist_to_db(db)
    assert first == 4
    assert second == 4

    count = db.execute(
        text("SELECT COUNT(*) FROM version_registry WHERE version_type = 'MODEL'")
    ).scalar_one()
    assert count == 4

    value = db.execute(
        text("SELECT version_value FROM version_registry WHERE version_key = 'model:finbert'")
    ).scalar_one()
    assert value == "finbert_v1"
