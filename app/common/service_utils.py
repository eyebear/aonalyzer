"""Shared, single-source-of-truth helpers used across analytics/data services.

Phases 7-12 each copied the same small helpers (symbol normalization, watchlist
loading, column probing, table materialization) into their own service classes.
These canonical implementations consolidate that duplication so every layer --
and Phase 13 onward -- shares identical, behavior-preserving logic.

The function bodies here are the exact behavior of the previously duplicated
implementations; service classes now delegate to these via thin wrappers.
"""

from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.database.base import Base

# Tables probed (in priority order) when resolving the active watchlist.
# ``tickers`` is the seeded source of truth and is normally found first; the
# remaining names make the helper resilient to alternative schemas.
WATCHLIST_TABLE_PRIORITY: list[str] = [
    "tickers",
    "watchlists",
    "watchlist_symbols",
    "user_watchlists",
]

SYMBOL_COLUMN_CANDIDATES: list[str] = ["symbol", "ticker", "ticker_symbol"]
ACTIVE_COLUMN_CANDIDATES: list[str] = ["is_active", "active", "enabled"]


def normalize_symbols(symbols: list[str]) -> list[str]:
    """Strip/upper-case symbols and de-duplicate while preserving order."""
    normalized: list[str] = []
    for symbol in symbols:
        clean = symbol.strip().upper()
        if clean and clean not in normalized:
            normalized.append(clean)
    return normalized


def select_first_available_column(
    columns: set[str],
    candidates: list[str],
) -> str | None:
    """Return the first candidate column name present in ``columns``."""
    for candidate in candidates:
        if candidate in columns:
            return candidate
    return None


def load_watchlist_symbols(db: Session) -> list[str]:
    """Load active watchlist symbols by introspecting known watchlist tables.

    Probes ``WATCHLIST_TABLE_PRIORITY`` in order, selecting the first table that
    yields symbols. Honors an ``is_active``-style column when present. Returns an
    empty list if no watchlist table/column is available.
    """
    inspector = inspect(db.get_bind())
    table_names = set(inspector.get_table_names())

    for table_name in WATCHLIST_TABLE_PRIORITY:
        if table_name not in table_names:
            continue

        columns = {col["name"] for col in inspector.get_columns(table_name)}

        symbol_column = select_first_available_column(columns, SYMBOL_COLUMN_CANDIDATES)
        if symbol_column is None:
            continue

        active_column = select_first_available_column(columns, ACTIVE_COLUMN_CANDIDATES)

        if active_column is None:
            rows = (
                db.execute(
                    text(
                        f"SELECT DISTINCT {symbol_column} AS symbol "
                        f"FROM {table_name} "
                        f"WHERE {symbol_column} IS NOT NULL "
                        f"ORDER BY {symbol_column}"
                    )
                )
                .mappings()
                .all()
            )
        else:
            rows = (
                db.execute(
                    text(
                        f"SELECT DISTINCT {symbol_column} AS symbol "
                        f"FROM {table_name} "
                        f"WHERE {symbol_column} IS NOT NULL "
                        f"AND {active_column} = :active_value "
                        f"ORDER BY {symbol_column}"
                    ),
                    {"active_value": True},
                )
                .mappings()
                .all()
            )

        symbols = normalize_symbols(
            [str(row["symbol"]) for row in rows if row.get("symbol") is not None]
        )
        if symbols:
            return symbols

    return []


def ensure_tables(db: Session) -> None:
    """Materialize ORM tables on the bound engine — test/dev fallback only.

    On PostgreSQL this is a deliberate no-op: the production schema is owned
    exclusively by Alembic (``alembic upgrade head``, applied automatically by
    the API container on startup). A genuinely missing table therefore
    surfaces as a clear "relation does not exist" database error instead of
    being silently created outside migration control.

    On any other dialect (the SQLite engines used by unit tests and ad-hoc
    local sessions) it still runs ``Base.metadata.create_all`` so those
    environments work without running migrations.
    """
    bind = db.get_bind()
    if bind.dialect.name == "postgresql":
        return
    Base.metadata.create_all(bind=bind)


__all__ = [
    "ACTIVE_COLUMN_CANDIDATES",
    "SYMBOL_COLUMN_CANDIDATES",
    "WATCHLIST_TABLE_PRIORITY",
    "ensure_tables",
    "load_watchlist_symbols",
    "normalize_symbols",
    "select_first_available_column",
]
