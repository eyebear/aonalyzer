from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.options.manual_option_ai_reader import ManualOptionAiReader
from app.options.manual_option_models import (
    ManualOptionSnapshotRecord,
    ParsedManualOptionInput,
)
from app.options.manual_option_parser import ManualOptionTextParser


class ManualOptionInputService:
    def __init__(
        self,
        parser: ManualOptionTextParser | None = None,
        ai_reader: ManualOptionAiReader | None = None,
    ) -> None:
        self.parser = parser or ManualOptionTextParser()
        self.ai_reader = ai_reader or ManualOptionAiReader()

    def create_manual_snapshot(
        self,
        db: Session,
        raw_text: str,
        symbol: str | None = None,
        source_name: str | None = None,
    ) -> ManualOptionSnapshotRecord:
        self.ensure_manual_option_tables(db)

        parsed = self.parser.parse(
            raw_text=raw_text,
            supplied_symbol=symbol,
            supplied_source_name=source_name,
        )

        now = datetime.now(timezone.utc)

        result = db.execute(
            text(
                """
                INSERT INTO manual_option_snapshots (
                    raw_text,
                    symbol,
                    source_name,
                    underlying_price,
                    expiration_date,
                    option_type,
                    strike,
                    bid,
                    ask,
                    last_price,
                    volume,
                    open_interest,
                    implied_volatility,
                    delta,
                    gamma,
                    theta,
                    vega,
                    rho,
                    dte,
                    mid_price,
                    spread_percent,
                    contract_cost,
                    breakeven,
                    breakeven_distance,
                    breakeven_distance_percent,
                    parser_confidence,
                    missing_fields_json,
                    parsed_fields_json,
                    data_quality_status,
                    ai_status,
                    ai_summary,
                    ai_analysis_json,
                    created_at,
                    updated_at
                )
                VALUES (
                    :raw_text,
                    :symbol,
                    :source_name,
                    :underlying_price,
                    :expiration_date,
                    :option_type,
                    :strike,
                    :bid,
                    :ask,
                    :last_price,
                    :volume,
                    :open_interest,
                    :implied_volatility,
                    :delta,
                    :gamma,
                    :theta,
                    :vega,
                    :rho,
                    :dte,
                    :mid_price,
                    :spread_percent,
                    :contract_cost,
                    :breakeven,
                    :breakeven_distance,
                    :breakeven_distance_percent,
                    :parser_confidence,
                    :missing_fields_json,
                    :parsed_fields_json,
                    :data_quality_status,
                    :ai_status,
                    :ai_summary,
                    :ai_analysis_json,
                    :created_at,
                    :updated_at
                )
                RETURNING id
                """
            ),
            self._parsed_to_insert_values(parsed, now),
        )

        snapshot_id = result.scalar_one()
        db.commit()

        snapshot = self.get_manual_snapshot_by_id(db=db, snapshot_id=snapshot_id)

        if snapshot is None:
            raise RuntimeError("Manual option snapshot was inserted but could not be read.")

        return snapshot

    def list_manual_snapshots(
        self,
        db: Session,
        symbol: str | None = None,
        limit: int = 100,
    ) -> list[ManualOptionSnapshotRecord]:
        self.ensure_manual_option_tables(db)

        normalized_limit = max(1, min(limit, 500))

        if symbol:
            rows = (
                db.execute(
                    text(
                        """
                        SELECT *
                        FROM manual_option_snapshots
                        WHERE symbol = :symbol
                        ORDER BY created_at DESC, id DESC
                        LIMIT :limit
                        """
                    ),
                    {
                        "symbol": symbol.upper(),
                        "limit": normalized_limit,
                    },
                )
                .mappings()
                .all()
            )
        else:
            rows = (
                db.execute(
                    text(
                        """
                        SELECT *
                        FROM manual_option_snapshots
                        ORDER BY created_at DESC, id DESC
                        LIMIT :limit
                        """
                    ),
                    {
                        "limit": normalized_limit,
                    },
                )
                .mappings()
                .all()
            )

        return [
            self._row_to_record(row)
            for row in rows
        ]

    def get_manual_snapshot_by_id(
        self,
        db: Session,
        snapshot_id: int,
    ) -> ManualOptionSnapshotRecord | None:
        self.ensure_manual_option_tables(db)

        row = (
            db.execute(
                text(
                    """
                    SELECT *
                    FROM manual_option_snapshots
                    WHERE id = :id
                    """
                ),
                {
                    "id": snapshot_id,
                },
            )
            .mappings()
            .one_or_none()
        )

        if row is None:
            return None

        return self._row_to_record(row)

    def analyze_manual_snapshot(
        self,
        db: Session,
        snapshot_id: int,
    ) -> ManualOptionSnapshotRecord:
        self.ensure_manual_option_tables(db)

        snapshot = self.get_manual_snapshot_by_id(
            db=db,
            snapshot_id=snapshot_id,
        )

        if snapshot is None:
            raise ValueError(f"Manual option snapshot {snapshot_id} was not found.")

        analysis = self.ai_reader.analyze_snapshot(snapshot)
        summary = analysis.get("plain_english_summary")

        db.execute(
            text(
                """
                UPDATE manual_option_snapshots
                SET ai_status = :ai_status,
                    ai_summary = :ai_summary,
                    ai_analysis_json = :ai_analysis_json,
                    updated_at = :updated_at
                WHERE id = :id
                """
            ),
            {
                "id": snapshot_id,
                "ai_status": "PLACEHOLDER_COMPLETE",
                "ai_summary": summary,
                "ai_analysis_json": json.dumps(analysis),
                "updated_at": datetime.now(timezone.utc),
            },
        )
        db.commit()

        updated_snapshot = self.get_manual_snapshot_by_id(
            db=db,
            snapshot_id=snapshot_id,
        )

        if updated_snapshot is None:
            raise RuntimeError("Manual option snapshot disappeared after analysis.")

        return updated_snapshot

    def ensure_manual_option_tables(self, db: Session) -> None:
        dialect_name = db.get_bind().dialect.name

        if dialect_name == "postgresql":
            self._ensure_postgresql_table(db)
        else:
            self._ensure_sqlite_table(db)

        db.commit()

    def _ensure_postgresql_table(self, db: Session) -> None:
        db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS manual_option_snapshots (
                    id SERIAL PRIMARY KEY,
                    raw_text TEXT NOT NULL,
                    symbol VARCHAR(50),
                    source_name VARCHAR(200),
                    underlying_price NUMERIC(18, 6),
                    expiration_date DATE,
                    option_type VARCHAR(20),
                    strike NUMERIC(18, 6),
                    bid NUMERIC(18, 6),
                    ask NUMERIC(18, 6),
                    last_price NUMERIC(18, 6),
                    volume INTEGER,
                    open_interest INTEGER,
                    implied_volatility NUMERIC(18, 8),
                    delta NUMERIC(18, 8),
                    gamma NUMERIC(18, 8),
                    theta NUMERIC(18, 8),
                    vega NUMERIC(18, 8),
                    rho NUMERIC(18, 8),
                    dte INTEGER,
                    mid_price NUMERIC(18, 6),
                    spread_percent NUMERIC(18, 8),
                    contract_cost NUMERIC(18, 6),
                    breakeven NUMERIC(18, 6),
                    breakeven_distance NUMERIC(18, 6),
                    breakeven_distance_percent NUMERIC(18, 8),
                    parser_confidence VARCHAR(20) NOT NULL,
                    missing_fields_json TEXT NOT NULL,
                    parsed_fields_json TEXT NOT NULL,
                    data_quality_status VARCHAR(80) NOT NULL,
                    ai_status VARCHAR(80),
                    ai_summary TEXT,
                    ai_analysis_json TEXT,
                    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
                    updated_at TIMESTAMP WITH TIME ZONE NOT NULL
                )
                """
            )
        )

        expected_columns = {
            "raw_text": "TEXT",
            "symbol": "VARCHAR(50)",
            "source_name": "VARCHAR(200)",
            "underlying_price": "NUMERIC(18, 6)",
            "expiration_date": "DATE",
            "option_type": "VARCHAR(20)",
            "strike": "NUMERIC(18, 6)",
            "bid": "NUMERIC(18, 6)",
            "ask": "NUMERIC(18, 6)",
            "last_price": "NUMERIC(18, 6)",
            "volume": "INTEGER",
            "open_interest": "INTEGER",
            "implied_volatility": "NUMERIC(18, 8)",
            "delta": "NUMERIC(18, 8)",
            "gamma": "NUMERIC(18, 8)",
            "theta": "NUMERIC(18, 8)",
            "vega": "NUMERIC(18, 8)",
            "rho": "NUMERIC(18, 8)",
            "dte": "INTEGER",
            "mid_price": "NUMERIC(18, 6)",
            "spread_percent": "NUMERIC(18, 8)",
            "contract_cost": "NUMERIC(18, 6)",
            "breakeven": "NUMERIC(18, 6)",
            "breakeven_distance": "NUMERIC(18, 6)",
            "breakeven_distance_percent": "NUMERIC(18, 8)",
            "parser_confidence": "VARCHAR(20)",
            "missing_fields_json": "TEXT",
            "parsed_fields_json": "TEXT",
            "data_quality_status": "VARCHAR(80)",
            "ai_status": "VARCHAR(80)",
            "ai_summary": "TEXT",
            "ai_analysis_json": "TEXT",
            "created_at": "TIMESTAMP WITH TIME ZONE",
            "updated_at": "TIMESTAMP WITH TIME ZONE",
        }

        self._add_missing_columns(
            db=db,
            table_name="manual_option_snapshots",
            expected_columns=expected_columns,
        )

    def _ensure_sqlite_table(self, db: Session) -> None:
        db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS manual_option_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    raw_text TEXT NOT NULL,
                    symbol VARCHAR(50),
                    source_name VARCHAR(200),
                    underlying_price FLOAT,
                    expiration_date DATE,
                    option_type VARCHAR(20),
                    strike FLOAT,
                    bid FLOAT,
                    ask FLOAT,
                    last_price FLOAT,
                    volume INTEGER,
                    open_interest INTEGER,
                    implied_volatility FLOAT,
                    delta FLOAT,
                    gamma FLOAT,
                    theta FLOAT,
                    vega FLOAT,
                    rho FLOAT,
                    dte INTEGER,
                    mid_price FLOAT,
                    spread_percent FLOAT,
                    contract_cost FLOAT,
                    breakeven FLOAT,
                    breakeven_distance FLOAT,
                    breakeven_distance_percent FLOAT,
                    parser_confidence VARCHAR(20) NOT NULL,
                    missing_fields_json TEXT NOT NULL,
                    parsed_fields_json TEXT NOT NULL,
                    data_quality_status VARCHAR(80) NOT NULL,
                    ai_status VARCHAR(80),
                    ai_summary TEXT,
                    ai_analysis_json TEXT,
                    created_at TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP NOT NULL
                )
                """
            )
        )

        expected_columns = {
            "raw_text": "TEXT",
            "symbol": "VARCHAR(50)",
            "source_name": "VARCHAR(200)",
            "underlying_price": "FLOAT",
            "expiration_date": "DATE",
            "option_type": "VARCHAR(20)",
            "strike": "FLOAT",
            "bid": "FLOAT",
            "ask": "FLOAT",
            "last_price": "FLOAT",
            "volume": "INTEGER",
            "open_interest": "INTEGER",
            "implied_volatility": "FLOAT",
            "delta": "FLOAT",
            "gamma": "FLOAT",
            "theta": "FLOAT",
            "vega": "FLOAT",
            "rho": "FLOAT",
            "dte": "INTEGER",
            "mid_price": "FLOAT",
            "spread_percent": "FLOAT",
            "contract_cost": "FLOAT",
            "breakeven": "FLOAT",
            "breakeven_distance": "FLOAT",
            "breakeven_distance_percent": "FLOAT",
            "parser_confidence": "VARCHAR(20)",
            "missing_fields_json": "TEXT",
            "parsed_fields_json": "TEXT",
            "data_quality_status": "VARCHAR(80)",
            "ai_status": "VARCHAR(80)",
            "ai_summary": "TEXT",
            "ai_analysis_json": "TEXT",
            "created_at": "TIMESTAMP",
            "updated_at": "TIMESTAMP",
        }

        self._add_missing_columns(
            db=db,
            table_name="manual_option_snapshots",
            expected_columns=expected_columns,
        )

    def _add_missing_columns(
        self,
        db: Session,
        table_name: str,
        expected_columns: dict[str, str],
    ) -> None:
        inspector = inspect(db.get_bind())

        if table_name not in inspector.get_table_names():
            return

        existing_columns = {
            column["name"]
            for column in inspector.get_columns(table_name)
        }

        for column_name, column_type in expected_columns.items():
            if column_name in existing_columns:
                continue

            db.execute(
                text(
                    f"ALTER TABLE {table_name} "
                    f"ADD COLUMN {column_name} {column_type}"
                )
            )

    def _parsed_to_insert_values(
        self,
        parsed: ParsedManualOptionInput,
        now: datetime,
    ) -> dict[str, Any]:
        return {
            "raw_text": parsed.raw_text,
            "symbol": parsed.symbol,
            "source_name": parsed.source_name,
            "underlying_price": parsed.underlying_price,
            "expiration_date": parsed.expiration_date,
            "option_type": parsed.option_type,
            "strike": parsed.strike,
            "bid": parsed.bid,
            "ask": parsed.ask,
            "last_price": parsed.last_price,
            "volume": parsed.volume,
            "open_interest": parsed.open_interest,
            "implied_volatility": parsed.implied_volatility,
            "delta": parsed.delta,
            "gamma": parsed.gamma,
            "theta": parsed.theta,
            "vega": parsed.vega,
            "rho": parsed.rho,
            "dte": parsed.dte,
            "mid_price": parsed.mid_price,
            "spread_percent": parsed.spread_percent,
            "contract_cost": parsed.contract_cost,
            "breakeven": parsed.breakeven,
            "breakeven_distance": parsed.breakeven_distance,
            "breakeven_distance_percent": parsed.breakeven_distance_percent,
            "parser_confidence": parsed.parser_confidence,
            "missing_fields_json": json.dumps(parsed.missing_fields),
            "parsed_fields_json": json.dumps(parsed.parsed_fields),
            "data_quality_status": parsed.data_quality_status,
            "ai_status": "NOT_ANALYZED",
            "ai_summary": None,
            "ai_analysis_json": None,
            "created_at": now,
            "updated_at": now,
        }

    def _row_to_record(self, row: Any) -> ManualOptionSnapshotRecord:
        return ManualOptionSnapshotRecord(
            id=int(row["id"]),
            raw_text=str(row["raw_text"]),
            symbol=self._optional_str(row.get("symbol")),
            source_name=self._optional_str(row.get("source_name")),
            underlying_price=self._optional_float(row.get("underlying_price")),
            expiration_date=self._optional_date(row.get("expiration_date")),
            option_type=self._optional_str(row.get("option_type")),
            strike=self._optional_float(row.get("strike")),
            bid=self._optional_float(row.get("bid")),
            ask=self._optional_float(row.get("ask")),
            last_price=self._optional_float(row.get("last_price")),
            volume=self._optional_int(row.get("volume")),
            open_interest=self._optional_int(row.get("open_interest")),
            implied_volatility=self._optional_float(row.get("implied_volatility")),
            delta=self._optional_float(row.get("delta")),
            gamma=self._optional_float(row.get("gamma")),
            theta=self._optional_float(row.get("theta")),
            vega=self._optional_float(row.get("vega")),
            rho=self._optional_float(row.get("rho")),
            dte=self._optional_int(row.get("dte")),
            mid_price=self._optional_float(row.get("mid_price")),
            spread_percent=self._optional_float(row.get("spread_percent")),
            contract_cost=self._optional_float(row.get("contract_cost")),
            breakeven=self._optional_float(row.get("breakeven")),
            breakeven_distance=self._optional_float(row.get("breakeven_distance")),
            breakeven_distance_percent=self._optional_float(
                row.get("breakeven_distance_percent")
            ),
            parser_confidence=str(row["parser_confidence"]),
            missing_fields=self._json_list(row.get("missing_fields_json")),
            parsed_fields=self._json_dict(row.get("parsed_fields_json")),
            data_quality_status=str(row["data_quality_status"]),
            ai_status=self._optional_str(row.get("ai_status")),
            ai_summary=self._optional_str(row.get("ai_summary")),
            ai_analysis_json=self._json_dict(row.get("ai_analysis_json")),
            created_at=self._optional_datetime(row.get("created_at")),
        )

    def _optional_str(self, value: Any) -> str | None:
        if value is None:
            return None

        text_value = str(value)

        if not text_value:
            return None

        return text_value

    def _optional_float(self, value: Any) -> float | None:
        if value is None:
            return None

        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _optional_int(self, value: Any) -> int | None:
        if value is None:
            return None

        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _optional_date(self, value: Any) -> date | None:
        if value is None:
            return None

        if isinstance(value, date) and not isinstance(value, datetime):
            return value

        if isinstance(value, datetime):
            return value.date()

        text_value = str(value)

        try:
            return datetime.fromisoformat(text_value).date()
        except ValueError:
            pass

        try:
            return datetime.strptime(text_value[:10], "%Y-%m-%d").date()
        except ValueError:
            return None

    def _optional_datetime(self, value: Any) -> datetime | None:
        if value is None:
            return None

        if isinstance(value, datetime):
            return value

        try:
            return datetime.fromisoformat(str(value))
        except ValueError:
            return None

    def _json_list(self, value: Any) -> list[str]:
        if value is None:
            return []

        try:
            parsed = json.loads(str(value))
        except json.JSONDecodeError:
            return []

        if not isinstance(parsed, list):
            return []

        return [
            str(item)
            for item in parsed
        ]

    def _json_dict(self, value: Any) -> dict[str, Any]:
        if value is None:
            return {}

        try:
            parsed = json.loads(str(value))
        except json.JSONDecodeError:
            return {}

        if not isinstance(parsed, dict):
            return {}

        return parsed