from __future__ import annotations

from sqlalchemy.orm import Session

from app.common.service_utils import ensure_tables, load_watchlist_symbols, normalize_symbols
from app.database.models import DailyPrice
from app.quant.technical_indicators import (
    average_true_range,
    bollinger_bands,
    exponential_moving_average,
    minimum_rows_for_any_indicator,
    moving_average_convergence_divergence,
    relative_strength_index,
    required_history_for_indicators,
    simple_moving_average,
    volume_ratio,
)
from app.quant.technical_models import (
    IndicatorValues,
    SnapshotComputeResult,
    TechnicalRefreshResult,
)
from app.quant.technical_snapshot_models import TechnicalSnapshot

SUFFICIENT = "SUFFICIENT"
INSUFFICIENT_PRICE_HISTORY = "INSUFFICIENT_PRICE_HISTORY"
INSUFFICIENT_INDICATOR_DATA = "INSUFFICIENT_INDICATOR_DATA"


class TechnicalAnalysisService:
    def __init__(self) -> None:
        self._required = required_history_for_indicators()
        self._minimum_rows = minimum_rows_for_any_indicator()

    def ensure_technical_tables(self, db: Session) -> None:
        # Test/dev fallback only — no-op on PostgreSQL (schema owned by Alembic).
        ensure_tables(db)

    def load_watchlist_symbols(self, db: Session) -> list[str]:
        """Match the loader pattern used by MarketDataService / NewsService."""
        return load_watchlist_symbols(db)

    def compute_for_symbol(
        self,
        db: Session,
        symbol: str,
    ) -> SnapshotComputeResult:
        self.ensure_technical_tables(db)

        clean_symbol = symbol.strip().upper()

        rows = (
            db.query(DailyPrice)
            .filter(DailyPrice.symbol == clean_symbol)
            .order_by(DailyPrice.price_date.asc())
            .all()
        )

        if len(rows) < self._minimum_rows:
            return SnapshotComputeResult(
                symbol=clean_symbol,
                snapshot_date=rows[-1].price_date if rows else None,
                source_record_count=len(rows),
                data_sufficiency_status=INSUFFICIENT_PRICE_HISTORY,
                indicators=None,
                reason=(
                    f"Need at least {self._minimum_rows} daily price rows "
                    f"to compute any indicator; found {len(rows)}."
                ),
            )

        closes = [float(row.close_price) for row in rows if row.close_price is not None]
        highs = [float(row.high_price) for row in rows if row.high_price is not None]
        lows = [float(row.low_price) for row in rows if row.low_price is not None]
        volumes = [
            float(row.volume) if row.volume is not None else 0.0
            for row in rows
        ]

        if len(closes) < self._minimum_rows:
            return SnapshotComputeResult(
                symbol=clean_symbol,
                snapshot_date=rows[-1].price_date,
                source_record_count=len(rows),
                data_sufficiency_status=INSUFFICIENT_PRICE_HISTORY,
                indicators=None,
                reason=(
                    f"After removing rows with missing close prices, found "
                    f"{len(closes)} valid rows (need {self._minimum_rows})."
                ),
            )

        indicators = self._compute_indicators(
            closes=closes,
            highs=highs,
            lows=lows,
            volumes=volumes,
        )

        if all(
            getattr(indicators, name) is None
            for name in (
                "sma_20",
                "sma_50",
                "sma_200",
                "ema_12",
                "ema_26",
                "rsi_14",
                "macd",
                "atr_14",
                "bollinger_middle",
                "volume_ratio_20",
            )
        ):
            sufficiency = INSUFFICIENT_INDICATOR_DATA
        elif indicators.insufficient_indicators:
            sufficiency = "PARTIAL"
        else:
            sufficiency = SUFFICIENT

        return SnapshotComputeResult(
            symbol=clean_symbol,
            snapshot_date=rows[-1].price_date,
            source_record_count=len(rows),
            data_sufficiency_status=sufficiency,
            indicators=indicators,
            reason=None,
        )

    def _compute_indicators(
        self,
        closes: list[float],
        highs: list[float],
        lows: list[float],
        volumes: list[float],
    ) -> IndicatorValues:
        insufficient: list[str] = []

        def record_if_none(name: str, value: float | None) -> float | None:
            if value is None:
                insufficient.append(name)
            return value

        sma_20 = record_if_none("sma_20", simple_moving_average(closes, 20))
        sma_50 = record_if_none("sma_50", simple_moving_average(closes, 50))
        sma_200 = record_if_none("sma_200", simple_moving_average(closes, 200))

        ema_12 = record_if_none("ema_12", exponential_moving_average(closes, 12))
        ema_26 = record_if_none("ema_26", exponential_moving_average(closes, 26))

        rsi_14 = record_if_none("rsi_14", relative_strength_index(closes, 14))

        macd_result = moving_average_convergence_divergence(closes, 12, 26, 9)
        if macd_result.macd is None:
            insufficient.append("macd")
        if macd_result.signal is None:
            insufficient.append("macd_signal")
        if macd_result.histogram is None:
            insufficient.append("macd_histogram")

        atr_14 = (
            None
            if len(highs) != len(closes) or len(lows) != len(closes)
            else record_if_none(
                "atr_14",
                average_true_range(highs, lows, closes, 14),
            )
        )
        if atr_14 is None and "atr_14" not in insufficient:
            insufficient.append("atr_14")

        bollinger_result = bollinger_bands(closes, 20, 2.0)
        if bollinger_result.upper is None:
            insufficient.append("bollinger_bands_20")

        vr_value = record_if_none("volume_ratio_20", volume_ratio(volumes, 20))

        return IndicatorValues(
            last_close=closes[-1] if closes else None,
            last_volume=volumes[-1] if volumes else None,
            sma_20=sma_20,
            sma_50=sma_50,
            sma_200=sma_200,
            ema_12=ema_12,
            ema_26=ema_26,
            rsi_14=rsi_14,
            macd=macd_result.macd,
            macd_signal=macd_result.signal,
            macd_histogram=macd_result.histogram,
            atr_14=atr_14,
            bollinger_upper=bollinger_result.upper,
            bollinger_middle=bollinger_result.middle,
            bollinger_lower=bollinger_result.lower,
            volume_ratio_20=vr_value,
            insufficient_indicators=insufficient,
        )

    def persist_snapshot(
        self,
        db: Session,
        result: SnapshotComputeResult,
    ) -> tuple[TechnicalSnapshot, bool]:
        """Upsert by (symbol, snapshot_date). Returns (row, inserted_flag)."""
        self.ensure_technical_tables(db)

        if result.snapshot_date is None:
            raise ValueError(
                "Cannot persist snapshot without a snapshot_date "
                "(no rows existed for this symbol)."
            )

        existing = (
            db.query(TechnicalSnapshot)
            .filter(TechnicalSnapshot.symbol == result.symbol)
            .filter(TechnicalSnapshot.snapshot_date == result.snapshot_date)
            .one_or_none()
        )

        indicators = result.indicators
        insufficient_json = (
            list(indicators.insufficient_indicators) if indicators else []
        )

        values = {
            "source": "daily_prices",
            "source_record_count": result.source_record_count,
            "last_close": indicators.last_close if indicators else None,
            "last_volume": indicators.last_volume if indicators else None,
            "sma_20": indicators.sma_20 if indicators else None,
            "sma_50": indicators.sma_50 if indicators else None,
            "sma_200": indicators.sma_200 if indicators else None,
            "ema_12": indicators.ema_12 if indicators else None,
            "ema_26": indicators.ema_26 if indicators else None,
            "rsi_14": indicators.rsi_14 if indicators else None,
            "macd": indicators.macd if indicators else None,
            "macd_signal": indicators.macd_signal if indicators else None,
            "macd_histogram": indicators.macd_histogram if indicators else None,
            "atr_14": indicators.atr_14 if indicators else None,
            "bollinger_upper": indicators.bollinger_upper if indicators else None,
            "bollinger_middle": indicators.bollinger_middle if indicators else None,
            "bollinger_lower": indicators.bollinger_lower if indicators else None,
            "volume_ratio_20": indicators.volume_ratio_20 if indicators else None,
            "data_sufficiency_status": result.data_sufficiency_status,
            "insufficient_indicators_json": insufficient_json,
            "notes": result.reason,
        }

        if existing is None:
            row = TechnicalSnapshot(
                symbol=result.symbol,
                snapshot_date=result.snapshot_date,
                **values,
            )
            db.add(row)
            db.flush()
            return row, True

        for key, value in values.items():
            setattr(existing, key, value)
        db.flush()
        return existing, False

    def refresh_technical_snapshots(
        self,
        db: Session,
        symbols: list[str] | None = None,
    ) -> TechnicalRefreshResult:
        self.ensure_technical_tables(db)

        normalized = self._normalize_symbols(
            symbols if symbols is not None else self.load_watchlist_symbols(db)
        )

        result = TechnicalRefreshResult(requested_symbols=normalized)

        if not normalized:
            db.commit()
            return result

        for symbol in normalized:
            try:
                compute = self.compute_for_symbol(db=db, symbol=symbol)
            except Exception as exc:
                result.failed_symbols.append(symbol)
                result.failed_reasons[symbol] = str(exc)
                continue

            result.per_symbol_results.append(compute.to_dict())

            if compute.data_sufficiency_status == INSUFFICIENT_PRICE_HISTORY:
                result.insufficient_symbols.append(symbol)
                continue

            if compute.snapshot_date is None:
                result.insufficient_symbols.append(symbol)
                continue

            try:
                _, inserted = self.persist_snapshot(db=db, result=compute)
            except Exception as exc:
                db.rollback()
                result.failed_symbols.append(symbol)
                result.failed_reasons[symbol] = str(exc)
                continue

            if inserted:
                result.snapshots_inserted += 1
            else:
                result.snapshots_updated += 1
            result.successful_symbols.append(symbol)

        db.commit()
        return result

    def _normalize_symbols(self, symbols: list[str]) -> list[str]:
        return normalize_symbols(symbols)


__all__ = [
    "INSUFFICIENT_INDICATOR_DATA",
    "INSUFFICIENT_PRICE_HISTORY",
    "SUFFICIENT",
    "TechnicalAnalysisService",
]
