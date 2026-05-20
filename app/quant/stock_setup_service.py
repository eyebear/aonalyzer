from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.common.service_utils import (
    ensure_tables,
    load_watchlist_symbols,
    normalize_symbols,
)
from app.database.models import DailyPrice
from app.quant.stock_setup_models import StockSetup
from app.quant.support_resistance import (
    MINIMUM_PRICE_ROWS_FOR_SWINGS,
    SETUP_DIRECTION_UNDEFINED,
    STOP_METHOD_UNDEFINED,
    SetupMath,
    SupportResistanceLevels,
    calculate_setup_math,
    detect_support_resistance,
)
from app.quant.technical_snapshot_models import TechnicalSnapshot

SUFFICIENT = "SUFFICIENT"
PARTIAL = "PARTIAL"
INSUFFICIENT_PRICE_HISTORY = "INSUFFICIENT_PRICE_HISTORY"
INSUFFICIENT_SETUP_DATA = "INSUFFICIENT_SETUP_DATA"

DEFAULT_PRICE_LOOKBACK_ROWS = 120


@dataclass(frozen=True)
class SetupComputation:
    symbol: str
    snapshot_date: date | None
    source_record_count: int
    data_sufficiency_status: str

    current_close: float | None
    levels: SupportResistanceLevels | None
    setup: SetupMath | None
    cached_indicators: dict[str, float | None] = field(default_factory=dict)
    insufficient_reasons: list[str] = field(default_factory=list)
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "snapshot_date": self.snapshot_date.isoformat()
            if self.snapshot_date is not None
            else None,
            "source_record_count": self.source_record_count,
            "data_sufficiency_status": self.data_sufficiency_status,
            "current_close": self.current_close,
            "levels": self.levels.to_dict() if self.levels else None,
            "setup": self.setup.to_dict() if self.setup else None,
            "cached_indicators": dict(self.cached_indicators),
            "insufficient_reasons": list(self.insufficient_reasons),
            "notes": self.notes,
        }


@dataclass
class StockSetupRefreshResult:
    requested_symbols: list[str] = field(default_factory=list)
    successful_symbols: list[str] = field(default_factory=list)
    insufficient_symbols: list[str] = field(default_factory=list)
    failed_symbols: list[str] = field(default_factory=list)

    snapshots_inserted: int = 0
    snapshots_updated: int = 0
    per_symbol_results: list[dict[str, Any]] = field(default_factory=list)
    failed_reasons: dict[str, str] = field(default_factory=dict)

    @property
    def records_created(self) -> int:
        return self.snapshots_inserted

    @property
    def records_updated(self) -> int:
        return self.snapshots_updated

    @property
    def records_failed(self) -> int:
        return len(self.failed_symbols)

    def to_dict(self) -> dict[str, Any]:
        return {
            "requested_symbols": self.requested_symbols,
            "successful_symbols": self.successful_symbols,
            "insufficient_symbols": self.insufficient_symbols,
            "failed_symbols": self.failed_symbols,
            "snapshots_inserted": self.snapshots_inserted,
            "snapshots_updated": self.snapshots_updated,
            "records_created": self.records_created,
            "records_updated": self.records_updated,
            "records_failed": self.records_failed,
            "per_symbol_results": self.per_symbol_results,
            "failed_reasons": self.failed_reasons,
        }


class StockSetupService:
    """Compute and persist swing/MA/ATR-based stock setup math.

    Phase 12 contract:
    - Inputs are stored ``daily_prices`` and the latest ``TechnicalSnapshot``.
    - Manual option data is never required; if a symbol has price history,
      a setup can be computed.
    - Insufficient inputs produce ``INSUFFICIENT_PRICE_HISTORY`` or
      ``INSUFFICIENT_SETUP_DATA`` cleanly; nothing is invented.
    """

    def __init__(
        self,
        price_lookback_rows: int = DEFAULT_PRICE_LOOKBACK_ROWS,
        swing_window: int = 2,
    ) -> None:
        self.price_lookback_rows = price_lookback_rows
        self.swing_window = swing_window

    def ensure_tables(self, db: Session) -> None:
        ensure_tables(db)

    def load_watchlist_symbols(self, db: Session) -> list[str]:
        return load_watchlist_symbols(db)

    def compute_for_symbol(
        self,
        db: Session,
        symbol: str,
    ) -> SetupComputation:
        self.ensure_tables(db)

        clean_symbol = symbol.strip().upper()

        rows = (
            db.query(DailyPrice)
            .filter(DailyPrice.symbol == clean_symbol)
            .order_by(DailyPrice.price_date.asc())
            .all()
        )

        if len(rows) < MINIMUM_PRICE_ROWS_FOR_SWINGS:
            return SetupComputation(
                symbol=clean_symbol,
                snapshot_date=rows[-1].price_date if rows else None,
                source_record_count=len(rows),
                data_sufficiency_status=INSUFFICIENT_PRICE_HISTORY,
                current_close=None,
                levels=None,
                setup=None,
                cached_indicators={},
                insufficient_reasons=[
                    f"Need at least {MINIMUM_PRICE_ROWS_FOR_SWINGS} daily "
                    f"price rows; found {len(rows)}."
                ],
                notes="No setup computed.",
            )

        # Use the most recent ``price_lookback_rows`` rows for swing detection.
        recent = rows[-self.price_lookback_rows :] if self.price_lookback_rows > 0 else rows

        highs = [float(r.high_price) for r in recent if r.high_price is not None]
        lows = [float(r.low_price) for r in recent if r.low_price is not None]
        closes = [float(r.close_price) for r in recent if r.close_price is not None]

        if (
            len(highs) < MINIMUM_PRICE_ROWS_FOR_SWINGS
            or len(lows) < MINIMUM_PRICE_ROWS_FOR_SWINGS
            or not closes
        ):
            return SetupComputation(
                symbol=clean_symbol,
                snapshot_date=rows[-1].price_date,
                source_record_count=len(rows),
                data_sufficiency_status=INSUFFICIENT_PRICE_HISTORY,
                current_close=None,
                levels=None,
                setup=None,
                cached_indicators={},
                insufficient_reasons=[
                    "Recent OHLC rows have too many missing values "
                    "to compute swings."
                ],
                notes="No setup computed.",
            )

        current_close = closes[-1]

        tech = (
            db.query(TechnicalSnapshot)
            .filter(TechnicalSnapshot.symbol == clean_symbol)
            .order_by(
                TechnicalSnapshot.snapshot_date.desc(),
                TechnicalSnapshot.id.desc(),
            )
            .first()
        )

        sma_20 = tech.sma_20 if tech else None
        sma_50 = tech.sma_50 if tech else None
        sma_200 = tech.sma_200 if tech else None
        atr_14 = tech.atr_14 if tech else None

        cached = {
            "sma_20": sma_20,
            "sma_50": sma_50,
            "sma_200": sma_200,
            "atr_14": atr_14,
        }

        levels = detect_support_resistance(
            highs=highs,
            lows=lows,
            current_close=current_close,
            sma_20=sma_20,
            sma_50=sma_50,
            sma_200=sma_200,
            swing_window=self.swing_window,
        )

        setup = calculate_setup_math(
            current_close=current_close,
            nearest_support=levels.nearest_support,
            nearest_resistance=levels.nearest_resistance,
            atr_14=atr_14,
        )

        combined_reasons = list(levels.insufficient_reasons) + list(setup.insufficient_reasons)

        if (
            setup.stop_price is None
            or setup.target_price is None
            or setup.risk_per_share is None
            or setup.reward_per_share is None
            or setup.direction == SETUP_DIRECTION_UNDEFINED
        ):
            sufficiency = INSUFFICIENT_SETUP_DATA
        elif combined_reasons:
            sufficiency = PARTIAL
        else:
            sufficiency = SUFFICIENT

        return SetupComputation(
            symbol=clean_symbol,
            snapshot_date=rows[-1].price_date,
            source_record_count=len(rows),
            data_sufficiency_status=sufficiency,
            current_close=current_close,
            levels=levels,
            setup=setup,
            cached_indicators=cached,
            insufficient_reasons=combined_reasons,
            notes=None,
        )

    def persist_setup(
        self,
        db: Session,
        computation: SetupComputation,
    ) -> tuple[StockSetup, bool]:
        self.ensure_tables(db)

        if computation.snapshot_date is None:
            raise ValueError(
                "Cannot persist a stock setup with no snapshot_date "
                "(no price rows existed for this symbol)."
            )

        existing = (
            db.query(StockSetup)
            .filter(StockSetup.symbol == computation.symbol)
            .filter(StockSetup.snapshot_date == computation.snapshot_date)
            .one_or_none()
        )

        levels = computation.levels
        setup = computation.setup
        cached = computation.cached_indicators

        values = {
            "source": "daily_prices+technical",
            "source_record_count": computation.source_record_count,
            "current_close": computation.current_close,
            "nearest_support": levels.nearest_support if levels else None,
            "nearest_resistance": levels.nearest_resistance if levels else None,
            "swing_low": levels.swing_low if levels else None,
            "swing_high": levels.swing_high if levels else None,
            "sma_20": cached.get("sma_20"),
            "sma_50": cached.get("sma_50"),
            "sma_200": cached.get("sma_200"),
            "atr_14": cached.get("atr_14"),
            "direction": setup.direction if setup else SETUP_DIRECTION_UNDEFINED,
            "entry_zone_low": setup.entry_zone_low if setup else None,
            "entry_zone_high": setup.entry_zone_high if setup else None,
            "target_price": setup.target_price if setup else None,
            "stop_price": setup.stop_price if setup else None,
            "stop_method": setup.stop_method if setup else STOP_METHOD_UNDEFINED,
            "risk_per_share": setup.risk_per_share if setup else None,
            "reward_per_share": setup.reward_per_share if setup else None,
            "stock_risk_reward": setup.stock_risk_reward if setup else None,
            "data_sufficiency_status": computation.data_sufficiency_status,
            "insufficient_reasons_json": list(computation.insufficient_reasons),
            "notes": computation.notes,
        }

        if existing is None:
            row = StockSetup(
                symbol=computation.symbol,
                snapshot_date=computation.snapshot_date,
                **values,
            )
            db.add(row)
            db.flush()
            return row, True

        for key, value in values.items():
            setattr(existing, key, value)
        db.flush()
        return existing, False

    def refresh_stock_setups(
        self,
        db: Session,
        symbols: list[str] | None = None,
    ) -> StockSetupRefreshResult:
        self.ensure_tables(db)

        normalized = self._normalize_symbols(
            symbols if symbols is not None else self.load_watchlist_symbols(db)
        )
        result = StockSetupRefreshResult(requested_symbols=normalized)

        if not normalized:
            db.commit()
            return result

        for symbol in normalized:
            try:
                computation = self.compute_for_symbol(db=db, symbol=symbol)
            except Exception as exc:
                result.failed_symbols.append(symbol)
                result.failed_reasons[symbol] = str(exc)
                continue

            result.per_symbol_results.append(computation.to_dict())

            if computation.data_sufficiency_status == INSUFFICIENT_PRICE_HISTORY:
                result.insufficient_symbols.append(symbol)
                # Still write a snapshot row with the insufficiency status so
                # downstream UIs can render a clean state, but only if we have
                # a snapshot_date.
                if computation.snapshot_date is not None:
                    try:
                        _, inserted = self.persist_setup(db=db, computation=computation)
                    except Exception as exc:
                        db.rollback()
                        result.failed_symbols.append(symbol)
                        result.failed_reasons[symbol] = str(exc)
                        continue
                    if inserted:
                        result.snapshots_inserted += 1
                    else:
                        result.snapshots_updated += 1
                continue

            try:
                _, inserted = self.persist_setup(db=db, computation=computation)
            except Exception as exc:
                db.rollback()
                result.failed_symbols.append(symbol)
                result.failed_reasons[symbol] = str(exc)
                continue

            if computation.data_sufficiency_status == INSUFFICIENT_SETUP_DATA:
                result.insufficient_symbols.append(symbol)
            else:
                result.successful_symbols.append(symbol)

            if inserted:
                result.snapshots_inserted += 1
            else:
                result.snapshots_updated += 1

        db.commit()
        return result

    def _normalize_symbols(self, symbols: list[str]) -> list[str]:
        return normalize_symbols(symbols)


__all__ = [
    "DEFAULT_PRICE_LOOKBACK_ROWS",
    "INSUFFICIENT_PRICE_HISTORY",
    "INSUFFICIENT_SETUP_DATA",
    "PARTIAL",
    "SUFFICIENT",
    "SetupComputation",
    "StockSetupRefreshResult",
    "StockSetupService",
]
