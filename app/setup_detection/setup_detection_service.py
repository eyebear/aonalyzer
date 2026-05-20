"""Stock setup detection orchestration (Phase 14, step 14.9).

Gathers the latest Phase 11 technical snapshot, Phase 12 setup math, and Phase
13 regime/sector context for each symbol, runs the deterministic detector, and
persists one ``StockSetupSignal`` per (symbol, snapshot_date). Stock-only and
non-blocking: option data is never required; missing inputs degrade to clean
``NO_TRADE`` / ``INSUFFICIENT_INPUT`` / ``PARTIAL`` states.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.common.service_utils import ensure_tables, load_watchlist_symbols, normalize_symbols
from app.core.config import AppSettings, get_settings
from app.market_regime.market_regime_models import (
    MarketRegimeSnapshot,
    SectorStrengthSnapshot,
)
from app.quant.stock_setup_models import StockSetup
from app.quant.technical_snapshot_models import TechnicalSnapshot
from app.setup_detection.setup_detection_models import StockSetupSignal
from app.setup_detection.setup_detector import (
    INSUFFICIENT_INPUT,
    SetupDetectionResult,
    SetupInputs,
    SetupParams,
    detect_setup,
)

SUFFICIENT = "SUFFICIENT"
PARTIAL = "PARTIAL"


@dataclass
class SetupSignalComputation:
    symbol: str
    snapshot_date: date | None
    data_sufficiency_status: str
    result: SetupDetectionResult

    close: float | None = None
    rsi_14: float | None = None
    atr_14: float | None = None
    risk_reward: float | None = None
    nearest_support: float | None = None
    nearest_resistance: float | None = None
    entry_zone_low: float | None = None
    entry_zone_high: float | None = None
    target_price: float | None = None
    stop_price: float | None = None

    regime_label: str | None = None
    sector_symbol: str | None = None
    sector_trend: str | None = None
    sector_rs_rank: int | None = None
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "snapshot_date": self.snapshot_date.isoformat()
            if self.snapshot_date
            else None,
            "data_sufficiency_status": self.data_sufficiency_status,
            "setup": self.result.to_dict(),
            "inputs": {
                "close": self.close,
                "rsi_14": self.rsi_14,
                "atr_14": self.atr_14,
                "risk_reward": self.risk_reward,
                "nearest_support": self.nearest_support,
                "nearest_resistance": self.nearest_resistance,
                "entry_zone_low": self.entry_zone_low,
                "entry_zone_high": self.entry_zone_high,
                "target_price": self.target_price,
                "stop_price": self.stop_price,
                "regime_label": self.regime_label,
                "sector_symbol": self.sector_symbol,
                "sector_trend": self.sector_trend,
                "sector_rs_rank": self.sector_rs_rank,
            },
            "notes": self.notes,
        }


@dataclass
class SetupDetectionRefreshResult:
    requested_symbols: list[str] = field(default_factory=list)
    successful_symbols: list[str] = field(default_factory=list)
    insufficient_symbols: list[str] = field(default_factory=list)
    failed_symbols: list[str] = field(default_factory=list)

    signals_inserted: int = 0
    signals_updated: int = 0
    per_symbol_results: list[dict[str, Any]] = field(default_factory=list)
    failed_reasons: dict[str, str] = field(default_factory=dict)

    @property
    def records_created(self) -> int:
        return self.signals_inserted

    @property
    def records_updated(self) -> int:
        return self.signals_updated

    @property
    def records_failed(self) -> int:
        return len(self.failed_symbols)

    def to_dict(self) -> dict[str, Any]:
        return {
            "requested_symbols": self.requested_symbols,
            "successful_symbols": self.successful_symbols,
            "insufficient_symbols": self.insufficient_symbols,
            "failed_symbols": self.failed_symbols,
            "signals_inserted": self.signals_inserted,
            "signals_updated": self.signals_updated,
            "records_created": self.records_created,
            "records_updated": self.records_updated,
            "records_failed": self.records_failed,
            "per_symbol_results": self.per_symbol_results,
            "failed_reasons": self.failed_reasons,
        }


class SetupDetectionService:
    def __init__(self, settings: AppSettings | None = None) -> None:
        self.settings = settings or get_settings()

    def ensure_tables(self, db: Session) -> None:
        ensure_tables(db)

    def load_watchlist_symbols(self, db: Session) -> list[str]:
        return load_watchlist_symbols(db)

    def _params(self) -> SetupParams:
        s = self.settings
        return SetupParams(
            rsi_oversold=s.setup_rsi_oversold,
            rsi_pullback_ceiling=s.setup_rsi_pullback_ceiling,
            pullback_atr_mult=s.setup_pullback_atr_mult,
            breakout_retest_tolerance=s.setup_breakout_retest_tolerance,
            breakdown_tolerance=s.setup_breakdown_tolerance,
            min_risk_reward=s.setup_min_risk_reward,
            sector_strong_max_rank=s.setup_sector_strong_max_rank,
            volume_confirm_ratio=s.setup_volume_confirm_ratio,
        )

    def _latest_regime_label(self, db: Session) -> str | None:
        regime = (
            db.query(MarketRegimeSnapshot)
            .order_by(
                MarketRegimeSnapshot.snapshot_date.desc(),
                MarketRegimeSnapshot.id.desc(),
            )
            .first()
        )
        return regime.regime_label if regime is not None else None

    def _sector_context(
        self, db: Session, symbol: str
    ) -> tuple[str | None, str | None, int | None]:
        """Return (sector_symbol, sector_trend, rs_rank) if a mapping exists."""
        sector_map = self.settings.setup_sector_map or {}
        sector_symbol = sector_map.get(symbol) or sector_map.get(symbol.upper())
        if not sector_symbol:
            return None, None, None

        benchmarks = self.settings.market_regime_benchmark_symbols
        primary_benchmark = benchmarks[0] if benchmarks else "SPY"

        sector_row = (
            db.query(SectorStrengthSnapshot)
            .filter(SectorStrengthSnapshot.sector_symbol == sector_symbol.upper())
            .filter(SectorStrengthSnapshot.benchmark_symbol == primary_benchmark.upper())
            .order_by(
                SectorStrengthSnapshot.snapshot_date.desc(),
                SectorStrengthSnapshot.id.desc(),
            )
            .first()
        )
        if sector_row is None:
            return sector_symbol.upper(), None, None
        return sector_symbol.upper(), sector_row.trend, sector_row.rs_rank

    def detect_for_symbol(self, db: Session, symbol: str) -> SetupSignalComputation:
        self.ensure_tables(db)
        clean = symbol.strip().upper()

        technical = (
            db.query(TechnicalSnapshot)
            .filter(TechnicalSnapshot.symbol == clean)
            .order_by(
                TechnicalSnapshot.snapshot_date.desc(),
                TechnicalSnapshot.id.desc(),
            )
            .first()
        )
        setup = (
            db.query(StockSetup)
            .filter(StockSetup.symbol == clean)
            .order_by(StockSetup.snapshot_date.desc(), StockSetup.id.desc())
            .first()
        )

        regime_label = self._latest_regime_label(db)
        sector_symbol, sector_trend, sector_rs_rank = self._sector_context(db, clean)

        close = technical.last_close if technical else None
        if close is None and setup is not None:
            close = setup.current_close

        inputs = SetupInputs(
            close=close,
            sma_20=technical.sma_20 if technical else None,
            sma_50=technical.sma_50 if technical else None,
            sma_200=technical.sma_200 if technical else None,
            rsi_14=technical.rsi_14 if technical else None,
            macd_histogram=technical.macd_histogram if technical else None,
            atr_14=technical.atr_14 if technical else None,
            volume_ratio=technical.volume_ratio_20 if technical else None,
            bollinger_lower=technical.bollinger_lower if technical else None,
            bollinger_upper=technical.bollinger_upper if technical else None,
            nearest_support=setup.nearest_support if setup else None,
            nearest_resistance=setup.nearest_resistance if setup else None,
            swing_high=setup.swing_high if setup else None,
            swing_low=setup.swing_low if setup else None,
            risk_reward=setup.stock_risk_reward if setup else None,
            regime_label=regime_label,
            sector_trend=sector_trend,
            sector_rs_rank=sector_rs_rank,
        )

        result = detect_setup(inputs, self._params())

        # Resolve the snapshot date from whichever source is available.
        snapshot_date = None
        if technical is not None:
            snapshot_date = technical.snapshot_date
        elif setup is not None:
            snapshot_date = setup.snapshot_date

        if technical is None:
            status = INSUFFICIENT_INPUT
        elif setup is None:
            status = PARTIAL
        else:
            status = result.data_sufficiency_status

        notes = None
        if setup is None and technical is not None:
            notes = "No Phase 12 setup math available; support/resistance/RR omitted."

        return SetupSignalComputation(
            symbol=clean,
            snapshot_date=snapshot_date,
            data_sufficiency_status=status,
            result=result,
            close=close,
            rsi_14=inputs.rsi_14,
            atr_14=inputs.atr_14,
            risk_reward=inputs.risk_reward,
            nearest_support=inputs.nearest_support,
            nearest_resistance=inputs.nearest_resistance,
            entry_zone_low=setup.entry_zone_low if setup else None,
            entry_zone_high=setup.entry_zone_high if setup else None,
            target_price=setup.target_price if setup else None,
            stop_price=setup.stop_price if setup else None,
            regime_label=regime_label,
            sector_symbol=sector_symbol,
            sector_trend=sector_trend,
            sector_rs_rank=sector_rs_rank,
            notes=notes,
        )

    def persist_signal(
        self,
        db: Session,
        computation: SetupSignalComputation,
    ) -> tuple[StockSetupSignal, bool]:
        self.ensure_tables(db)

        if computation.snapshot_date is None:
            raise ValueError(
                "Cannot persist a setup signal with no snapshot_date "
                "(no technical snapshot or stock setup existed for this symbol)."
            )

        existing = (
            db.query(StockSetupSignal)
            .filter(StockSetupSignal.symbol == computation.symbol)
            .filter(StockSetupSignal.snapshot_date == computation.snapshot_date)
            .one_or_none()
        )

        result = computation.result
        values = {
            "source": "technical+setup+regime",
            "setup_type": result.setup_type,
            "direction": result.direction,
            "score": result.score,
            "close": computation.close,
            "rsi_14": computation.rsi_14,
            "atr_14": computation.atr_14,
            "risk_reward": computation.risk_reward,
            "nearest_support": computation.nearest_support,
            "nearest_resistance": computation.nearest_resistance,
            "entry_zone_low": computation.entry_zone_low,
            "entry_zone_high": computation.entry_zone_high,
            "target_price": computation.target_price,
            "stop_price": computation.stop_price,
            "regime_label": computation.regime_label,
            "sector_symbol": computation.sector_symbol,
            "sector_trend": computation.sector_trend,
            "sector_rs_rank": computation.sector_rs_rank,
            "data_sufficiency_status": computation.data_sufficiency_status,
            "reasons_json": list(result.reasons),
            "components_json": dict(result.components),
            "notes": computation.notes,
        }

        if existing is None:
            row = StockSetupSignal(
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

    def refresh_setup_signals(
        self,
        db: Session,
        symbols: list[str] | None = None,
    ) -> SetupDetectionRefreshResult:
        self.ensure_tables(db)

        normalized = normalize_symbols(
            symbols if symbols is not None else self.load_watchlist_symbols(db)
        )
        result = SetupDetectionRefreshResult(requested_symbols=normalized)

        if not normalized:
            db.commit()
            return result

        for symbol in normalized:
            try:
                computation = self.detect_for_symbol(db=db, symbol=symbol)
            except Exception as exc:
                result.failed_symbols.append(symbol)
                result.failed_reasons[symbol] = str(exc)
                continue

            result.per_symbol_results.append(computation.to_dict())

            # No date to key the row on -> count as insufficient, do not invent.
            if computation.snapshot_date is None:
                result.insufficient_symbols.append(symbol)
                continue

            try:
                _, inserted = self.persist_signal(db=db, computation=computation)
            except Exception as exc:
                db.rollback()
                result.failed_symbols.append(symbol)
                result.failed_reasons[symbol] = str(exc)
                continue

            if inserted:
                result.signals_inserted += 1
            else:
                result.signals_updated += 1

            if computation.data_sufficiency_status == INSUFFICIENT_INPUT:
                result.insufficient_symbols.append(symbol)
            else:
                result.successful_symbols.append(symbol)

        db.commit()
        return result


__all__ = [
    "PARTIAL",
    "SUFFICIENT",
    "SetupDetectionRefreshResult",
    "SetupDetectionService",
    "SetupSignalComputation",
]
