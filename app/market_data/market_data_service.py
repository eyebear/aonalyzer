from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.data_quality.data_quality_models import DataFreshness
from app.data_quality.data_sufficiency_labels import DataFreshnessStatus
from app.market_data.market_data_models import (
    DailyPrice,
    FailedTickerLog,
    IntradayPrice,
)


@dataclass(frozen=True)
class OHLCVRow:
    symbol: str
    timestamp: datetime | date
    open_price: float | None
    high_price: float | None
    low_price: float | None
    close_price: float | None
    adjusted_close: float | None
    volume: float | None
    source: str = "yfinance"


@dataclass
class MarketDataRefreshResult:
    requested_symbols: list[str] = field(default_factory=list)
    successful_symbols: list[str] = field(default_factory=list)
    failed_symbols: list[str] = field(default_factory=list)

    daily_rows_inserted: int = 0
    daily_rows_updated: int = 0
    intraday_rows_inserted: int = 0
    intraday_rows_updated: int = 0

    failed_reasons: dict[str, str] = field(default_factory=dict)

    @property
    def records_created(self) -> int:
        return self.daily_rows_inserted + self.intraday_rows_inserted

    @property
    def records_updated(self) -> int:
        return self.daily_rows_updated + self.intraday_rows_updated

    @property
    def total_records_touched(self) -> int:
        return self.records_created + self.records_updated

    def to_dict(self) -> dict[str, Any]:
        return {
            "requested_symbols": self.requested_symbols,
            "successful_symbols": self.successful_symbols,
            "failed_symbols": self.failed_symbols,
            "daily_rows_inserted": self.daily_rows_inserted,
            "daily_rows_updated": self.daily_rows_updated,
            "intraday_rows_inserted": self.intraday_rows_inserted,
            "intraday_rows_updated": self.intraday_rows_updated,
            "records_created": self.records_created,
            "records_updated": self.records_updated,
            "total_records_touched": self.total_records_touched,
            "failed_reasons": self.failed_reasons,
        }


class YFinanceMarketDataClient:
    source_name = "yfinance"

    def fetch_daily_ohlcv(
        self,
        symbol: str,
        period: str = "6mo",
    ) -> list[OHLCVRow]:
        yfinance_download_rows = self._fetch_with_download(
            symbol=symbol,
            period=period,
            interval="1d",
            timestamp_column_name="Date",
        )

        if yfinance_download_rows:
            return yfinance_download_rows

        ticker_history_rows = self._fetch_with_ticker_history(
            symbol=symbol,
            period=period,
            interval="1d",
            timestamp_column_name="Date",
        )

        if ticker_history_rows:
            return ticker_history_rows

        return self._fetch_with_yahoo_chart_api(
            symbol=symbol,
            period=period,
            interval="1d",
        )

    def fetch_intraday_ohlcv(
        self,
        symbol: str,
        period: str = "1d",
        interval: str = "5m",
    ) -> list[OHLCVRow]:
        yfinance_download_rows = self._fetch_with_download(
            symbol=symbol,
            period=period,
            interval=interval,
            timestamp_column_name="Datetime",
        )

        if yfinance_download_rows:
            return yfinance_download_rows

        ticker_history_rows = self._fetch_with_ticker_history(
            symbol=symbol,
            period=period,
            interval=interval,
            timestamp_column_name="Datetime",
        )

        if ticker_history_rows:
            return ticker_history_rows

        return self._fetch_with_yahoo_chart_api(
            symbol=symbol,
            period=period,
            interval=interval,
        )

    def _fetch_with_download(
        self,
        symbol: str,
        period: str,
        interval: str,
        timestamp_column_name: str,
    ) -> list[OHLCVRow]:
        try:
            import yfinance as yf

            dataframe = yf.download(
                tickers=symbol,
                period=period,
                interval=interval,
                auto_adjust=False,
                progress=False,
                threads=False,
            )

            return self._dataframe_to_ohlcv_rows(
                symbol=symbol,
                dataframe=dataframe,
                timestamp_column_name=timestamp_column_name,
                source="yfinance",
            )
        except Exception:
            return []

    def _fetch_with_ticker_history(
        self,
        symbol: str,
        period: str,
        interval: str,
        timestamp_column_name: str,
    ) -> list[OHLCVRow]:
        try:
            import yfinance as yf

            ticker = yf.Ticker(symbol)
            history = ticker.history(
                period=period,
                interval=interval,
                auto_adjust=False,
            )

            return self._dataframe_to_ohlcv_rows(
                symbol=symbol,
                dataframe=history,
                timestamp_column_name=timestamp_column_name,
                source="yfinance",
            )
        except Exception:
            return []

    def _fetch_with_yahoo_chart_api(
        self,
        symbol: str,
        period: str,
        interval: str,
    ) -> list[OHLCVRow]:
        query = urlencode(
            {
                "range": period,
                "interval": interval,
                "includePrePost": "false",
                "events": "div,splits",
            }
        )

        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol.upper()}?{query}"

        request = Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/json,text/plain,*/*",
            },
        )

        try:
            with urlopen(request, timeout=20) as response:
                raw_text = response.read().decode("utf-8")

            parsed = json.loads(raw_text)

            chart = parsed.get("chart", {})
            error = chart.get("error")
            if error is not None:
                return []

            result_list = chart.get("result") or []
            if not result_list:
                return []

            result = result_list[0]
            timestamps = result.get("timestamp") or []

            indicators = result.get("indicators") or {}
            quote_list = indicators.get("quote") or []
            if not quote_list:
                return []

            quote = quote_list[0]

            open_values = quote.get("open") or []
            high_values = quote.get("high") or []
            low_values = quote.get("low") or []
            close_values = quote.get("close") or []
            volume_values = quote.get("volume") or []

            adjclose_values: list[Any] = []
            adjclose_list = indicators.get("adjclose") or []
            if adjclose_list:
                adjclose_values = adjclose_list[0].get("adjclose") or []

            rows: list[OHLCVRow] = []

            for index, timestamp_value in enumerate(timestamps):
                timestamp = datetime.fromtimestamp(
                    int(timestamp_value),
                    tz=timezone.utc,
                )

                open_price = self._safe_list_value(open_values, index)
                high_price = self._safe_list_value(high_values, index)
                low_price = self._safe_list_value(low_values, index)
                close_price = self._safe_list_value(close_values, index)
                volume = self._safe_list_value(volume_values, index)
                adjusted_close = self._safe_list_value(adjclose_values, index)

                if adjusted_close is None:
                    adjusted_close = close_price

                row = OHLCVRow(
                    symbol=symbol.upper(),
                    timestamp=timestamp,
                    open_price=open_price,
                    high_price=high_price,
                    low_price=low_price,
                    close_price=close_price,
                    adjusted_close=adjusted_close,
                    volume=volume,
                    source="yahoo_chart",
                )

                if self._row_has_price_data(row):
                    rows.append(row)

            return rows

        except Exception as exc:
            print(f"Yahoo Chart API fallback failed for {symbol}: {exc}")
            return []

    def _dataframe_to_ohlcv_rows(
        self,
        symbol: str,
        dataframe: Any,
        timestamp_column_name: str,
        source: str,
    ) -> list[OHLCVRow]:
        if dataframe is None or dataframe.empty:
            return []

        normalized = dataframe.reset_index()

        if hasattr(normalized.columns, "nlevels") and normalized.columns.nlevels > 1:
            normalized.columns = [
                column[0] if isinstance(column, tuple) else column
                for column in normalized.columns
            ]

        rows: list[OHLCVRow] = []

        for _, row in normalized.iterrows():
            timestamp_value = row.get(timestamp_column_name)

            if timestamp_value is None:
                timestamp_value = row.iloc[0]

            timestamp = self._to_datetime_or_date(timestamp_value)

            ohlcv_row = OHLCVRow(
                symbol=symbol.upper(),
                timestamp=timestamp,
                open_price=self._to_float_or_none(row.get("Open")),
                high_price=self._to_float_or_none(row.get("High")),
                low_price=self._to_float_or_none(row.get("Low")),
                close_price=self._to_float_or_none(row.get("Close")),
                adjusted_close=self._to_float_or_none(row.get("Adj Close")),
                volume=self._to_float_or_none(row.get("Volume")),
                source=source,
            )

            if self._row_has_price_data(ohlcv_row):
                rows.append(ohlcv_row)

        return rows

    def _row_has_price_data(self, row: OHLCVRow) -> bool:
        return any(
            value is not None
            for value in [
                row.open_price,
                row.high_price,
                row.low_price,
                row.close_price,
            ]
        )

    def _safe_list_value(
        self,
        values: list[Any],
        index: int,
    ) -> float | None:
        if index >= len(values):
            return None

        return self._to_float_or_none(values[index])

    def _to_float_or_none(self, value: Any) -> float | None:
        if value is None:
            return None

        try:
            if value != value:
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    def _to_datetime_or_date(self, value: Any) -> datetime | date:
        if hasattr(value, "to_pydatetime"):
            converted = value.to_pydatetime()
        else:
            converted = value

        if isinstance(converted, datetime):
            if converted.tzinfo is None:
                return converted.replace(tzinfo=timezone.utc)
            return converted

        if isinstance(converted, date):
            return converted

        parsed = datetime.fromisoformat(str(converted))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)

        return parsed


class MarketDataService:
    def __init__(
        self,
        client: YFinanceMarketDataClient | None = None,
        source: str = "yfinance",
    ) -> None:
        self.client = client or YFinanceMarketDataClient()
        self.source = source

    def load_watchlist_symbols(self, db: Session) -> list[str]:
        table_priority = [
            "tickers",
            "watchlists",
            "watchlist_symbols",
            "user_watchlists",
        ]

        inspector = inspect(db.get_bind())
        table_names = set(inspector.get_table_names())

        for table_name in table_priority:
            if table_name not in table_names:
                continue

            symbols = self._load_symbols_from_table(
                db=db,
                inspector=inspector,
                table_name=table_name,
            )

            if symbols:
                return symbols

        return []

    def refresh_market_data(
        self,
        db: Session,
        symbols: list[str] | None = None,
        include_daily: bool = True,
        include_intraday: bool = True,
        daily_period: str = "6mo",
        intraday_period: str = "1d",
        intraday_interval: str = "5m",
    ) -> MarketDataRefreshResult:
        selected_symbols = self._normalize_symbols(
            symbols if symbols is not None else self.load_watchlist_symbols(db)
        )

        result = MarketDataRefreshResult(requested_symbols=selected_symbols)

        if not selected_symbols:
            self._update_data_freshness(
                db=db,
                data_category="market_data",
                status=DataFreshnessStatus.MISSING,
                details={
                    "reason": "No watchlist symbols are available for market data refresh."
                },
            )
            db.commit()
            return result

        for symbol in selected_symbols:
            symbol_success = False

            try:
                if include_daily:
                    daily_rows = self.client.fetch_daily_ohlcv(
                        symbol=symbol,
                        period=daily_period,
                    )
                    daily_inserted, daily_updated = self._store_daily_prices(
                        db=db,
                        rows=daily_rows,
                    )
                    result.daily_rows_inserted += daily_inserted
                    result.daily_rows_updated += daily_updated

                    if daily_rows:
                        symbol_success = True

                if include_intraday:
                    intraday_rows = self.client.fetch_intraday_ohlcv(
                        symbol=symbol,
                        period=intraday_period,
                        interval=intraday_interval,
                    )
                    intraday_inserted, intraday_updated = self._store_intraday_prices(
                        db=db,
                        rows=intraday_rows,
                        interval=intraday_interval,
                    )
                    result.intraday_rows_inserted += intraday_inserted
                    result.intraday_rows_updated += intraday_updated

                    if intraday_rows:
                        symbol_success = True

                if symbol_success:
                    result.successful_symbols.append(symbol)
                else:
                    reason = "No market data rows were returned."
                    result.failed_symbols.append(symbol)
                    result.failed_reasons[symbol] = reason
                    self._log_failed_ticker(
                        db=db,
                        symbol=symbol,
                        data_category="market_data",
                        reason=reason,
                    )

            except Exception as exc:
                reason = str(exc)
                result.failed_symbols.append(symbol)
                result.failed_reasons[symbol] = reason
                self._log_failed_ticker(
                    db=db,
                    symbol=symbol,
                    data_category="market_data",
                    reason=reason,
                )

        if result.successful_symbols:
            self._update_data_freshness(
                db=db,
                data_category="market_data",
                status=DataFreshnessStatus.FRESH,
                details=result.to_dict(),
            )
        else:
            self._update_data_freshness(
                db=db,
                data_category="market_data",
                status=DataFreshnessStatus.MISSING,
                details=result.to_dict(),
            )

        db.commit()
        return result

    def _store_daily_prices(
        self,
        db: Session,
        rows: list[OHLCVRow],
    ) -> tuple[int, int]:
        inserted = 0
        updated = 0

        for row in rows:
            row_source = row.source or self.source
            price_date = self._as_date(row.timestamp)

            existing = (
                db.query(DailyPrice)
                .filter(DailyPrice.symbol == row.symbol.upper())
                .filter(DailyPrice.price_date == price_date)
                .filter(DailyPrice.source == row_source)
                .one_or_none()
            )

            if existing is None:
                db.add(
                    DailyPrice(
                        symbol=row.symbol.upper(),
                        price_date=price_date,
                        open_price=row.open_price,
                        high_price=row.high_price,
                        low_price=row.low_price,
                        close_price=row.close_price,
                        adjusted_close_price=row.adjusted_close,
                        volume=row.volume,
                        source=row_source,
                    )
                )
                inserted += 1
            else:
                existing.open_price = row.open_price
                existing.high_price = row.high_price
                existing.low_price = row.low_price
                existing.close_price = row.close_price
                existing.adjusted_close_price = row.adjusted_close
                existing.volume = row.volume
                updated += 1

        return inserted, updated

    def _store_intraday_prices(
        self,
        db: Session,
        rows: list[OHLCVRow],
        interval: str,
    ) -> tuple[int, int]:
        inserted = 0
        updated = 0

        for row in rows:
            row_source = row.source or self.source
            price_time = self._as_datetime(row.timestamp)

            existing = (
                db.query(IntradayPrice)
                .filter(IntradayPrice.symbol == row.symbol.upper())
                .filter(IntradayPrice.price_time == price_time)
                .filter(IntradayPrice.interval == interval)
                .filter(IntradayPrice.source == row_source)
                .one_or_none()
            )

            if existing is None:
                db.add(
                    IntradayPrice(
                        symbol=row.symbol.upper(),
                        price_time=price_time,
                        interval=interval,
                        open_price=row.open_price,
                        high_price=row.high_price,
                        low_price=row.low_price,
                        close_price=row.close_price,
                        volume=row.volume,
                        source=row_source,
                    )
                )
                inserted += 1
            else:
                existing.open_price = row.open_price
                existing.high_price = row.high_price
                existing.low_price = row.low_price
                existing.close_price = row.close_price
                existing.volume = row.volume
                updated += 1

        return inserted, updated

    def _log_failed_ticker(
        self,
        db: Session,
        symbol: str,
        data_category: str,
        reason: str,
    ) -> None:
        db.add(
            FailedTickerLog(
                symbol=symbol.upper(),
                data_category=data_category,
                source=self.source,
                reason=reason,
            )
        )

    def _update_data_freshness(
        self,
        db: Session,
        data_category: str,
        status: DataFreshnessStatus,
        details: dict[str, Any] | None = None,
    ) -> None:
        now = datetime.now(timezone.utc)

        existing = (
            db.query(DataFreshness)
            .filter(DataFreshness.data_category == data_category)
            .one_or_none()
        )

        if existing is None:
            db.add(
                DataFreshness(
                    data_category=data_category,
                    latest_success_at=now
                    if status == DataFreshnessStatus.FRESH
                    else None,
                    freshness_status=status.value,
                    max_age_minutes=30,
                    last_checked_at=now,
                    details_json=details or {},
                )
            )
            return

        if status == DataFreshnessStatus.FRESH:
            existing.latest_success_at = now

        existing.freshness_status = status.value
        existing.last_checked_at = now
        existing.details_json = details or {}

    def _load_symbols_from_table(
        self,
        db: Session,
        inspector: Any,
        table_name: str,
    ) -> list[str]:
        columns = {
            column["name"]
            for column in inspector.get_columns(table_name)
        }

        symbol_column = self._select_first_available_column(
            columns=columns,
            candidates=["symbol", "ticker", "ticker_symbol"],
        )

        if symbol_column is None:
            return []

        active_column = self._select_first_available_column(
            columns=columns,
            candidates=["is_active", "active", "enabled"],
        )

        if active_column is None:
            sql = text(
                f"SELECT DISTINCT {symbol_column} AS symbol FROM {table_name} "
                f"WHERE {symbol_column} IS NOT NULL "
                f"ORDER BY {symbol_column}"
            )
            rows = db.execute(sql).mappings().all()
        else:
            sql = text(
                f"SELECT DISTINCT {symbol_column} AS symbol FROM {table_name} "
                f"WHERE {symbol_column} IS NOT NULL "
                f"AND {active_column} = :active_value "
                f"ORDER BY {symbol_column}"
            )
            rows = db.execute(sql, {"active_value": True}).mappings().all()

        return self._normalize_symbols(
            [
                str(row["symbol"])
                for row in rows
                if row.get("symbol") is not None
            ]
        )

    def _select_first_available_column(
        self,
        columns: set[str],
        candidates: list[str],
    ) -> str | None:
        for candidate in candidates:
            if candidate in columns:
                return candidate
        return None

    def _normalize_symbols(self, symbols: list[str]) -> list[str]:
        normalized = []

        for symbol in symbols:
            clean_symbol = symbol.strip().upper()
            if clean_symbol and clean_symbol not in normalized:
                normalized.append(clean_symbol)

        return normalized

    def _as_date(self, value: datetime | date) -> date:
        if isinstance(value, datetime):
            return value.date()
        return value

    def _as_datetime(self, value: datetime | date) -> datetime:
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value

        return datetime(
            value.year,
            value.month,
            value.day,
            tzinfo=timezone.utc,
        )