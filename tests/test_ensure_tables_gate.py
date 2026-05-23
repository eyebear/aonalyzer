"""The runtime schema is owned by Alembic on PostgreSQL.

``ensure_tables`` must never lazily create tables on a PostgreSQL bind (a
missing table should surface as a clear database error, not be silently
created outside migration control). On SQLite (unit tests, ad-hoc dev
sessions) it must keep materializing the ORM metadata.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.common.service_utils import ensure_tables
from app.database import registry  # noqa: F401  (registers all ORM models on Base.metadata)


def test_ensure_tables_is_noop_on_postgresql() -> None:
    bind = MagicMock()
    bind.dialect.name = "postgresql"
    db = MagicMock()
    db.get_bind.return_value = bind

    with patch("app.common.service_utils.Base") as base:
        ensure_tables(db)

    base.metadata.create_all.assert_not_called()


def test_ensure_tables_creates_schema_on_sqlite() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session = sessionmaker(bind=engine)()
    try:
        assert inspect(engine).get_table_names() == []
        ensure_tables(session)
        assert "tickers" in inspect(engine).get_table_names()
    finally:
        session.close()
