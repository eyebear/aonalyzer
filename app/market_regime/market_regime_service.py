"""Market regime & sector strength orchestration (Phase 13, step 13.10).

Reads stored ``daily_prices`` (the same source the technical/stock-setup layers
use), computes the broad-market regime and sector relative strength via the pure
logic modules, and persists dated snapshots. Option data is never required and
never consulted here -- this layer supports both stock-only and option-aware
decisions. Missing regime inputs degrade to explicit non-blocking states.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.common.service_utils import ensure_tables
from app.core.config import AppSettings, get_settings
from app.database.models import DailyPrice
from app.market_regime.market_regime_models import (
    MarketRegimeSnapshot,
    SectorStrengthSnapshot,
)
from app.market_regime.regime_logic import (
    TREND_INSUFFICIENT,
    VIX_UNKNOWN,
    TrendResult,
    YieldResult,
    classify_trend,
    classify_vix,
    classify_yield_pressure,
    composite_regime,
)
from app.market_regime.sector_strength import (
    SectorStrengthResult,
    assign_ranks,
    compute_relative_strength,
)

SUFFICIENT = "SUFFICIENT"
PARTIAL = "PARTIAL"
INSUFFICIENT_PRICE_HISTORY = "INSUFFICIENT_PRICE_HISTORY"

# How many recent daily rows to pull per symbol (enough for the slow SMA).
DEFAULT_PRICE_LOOKBACK_ROWS = 260


@dataclass
class RegimeComputation:
    snapshot_date: date | None
    source_record_count: int
    data_sufficiency_status: str

    spy: TrendResult
    qqq: TrendResult
    iwm: TrendResult

    vix_symbol: str
    vix_level: float | None
    vix_state: str

    yield_symbol: str
    yield_result: YieldResult

    regime_label: str
    regime_score: int
    uptrend_count: int
    downtrend_count: int
    regime_components: dict[str, int] = field(default_factory=dict)

    insufficient_reasons: list[str] = field(default_factory=list)
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_date": self.snapshot_date.isoformat()
            if self.snapshot_date
            else None,
            "source_record_count": self.source_record_count,
            "data_sufficiency_status": self.data_sufficiency_status,
            "spy": self.spy.to_dict(),
            "qqq": self.qqq.to_dict(),
            "iwm": self.iwm.to_dict(),
            "vix": {
                "symbol": self.vix_symbol,
                "level": self.vix_level,
                "state": self.vix_state,
            },
            "yield": {"symbol": self.yield_symbol, **self.yield_result.to_dict()},
            "regime": {
                "regime_label": self.regime_label,
                "regime_score": self.regime_score,
                "uptrend_count": self.uptrend_count,
                "downtrend_count": self.downtrend_count,
                "components": dict(self.regime_components),
            },
            "insufficient_reasons": list(self.insufficient_reasons),
            "notes": self.notes,
        }


@dataclass
class MarketRegimeRefreshResult:
    snapshot_date: date | None = None
    regime_label: str = "UNKNOWN"
    data_sufficiency_status: str = "UNKNOWN"

    regime_inserted: int = 0
    regime_updated: int = 0
    sectors_inserted: int = 0
    sectors_updated: int = 0
    sector_count: int = 0

    fetched_symbols: list[str] = field(default_factory=list)
    regime: dict[str, Any] = field(default_factory=dict)
    sectors: list[dict[str, Any]] = field(default_factory=list)
    failed_reasons: dict[str, str] = field(default_factory=dict)

    @property
    def records_created(self) -> int:
        return self.regime_inserted + self.sectors_inserted

    @property
    def records_updated(self) -> int:
        return self.regime_updated + self.sectors_updated

    @property
    def records_failed(self) -> int:
        return len(self.failed_reasons)

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_date": self.snapshot_date.isoformat()
            if self.snapshot_date
            else None,
            "regime_label": self.regime_label,
            "data_sufficiency_status": self.data_sufficiency_status,
            "regime_inserted": self.regime_inserted,
            "regime_updated": self.regime_updated,
            "sectors_inserted": self.sectors_inserted,
            "sectors_updated": self.sectors_updated,
            "sector_count": self.sector_count,
            "records_created": self.records_created,
            "records_updated": self.records_updated,
            "records_failed": self.records_failed,
            "fetched_symbols": list(self.fetched_symbols),
            "regime": self.regime,
            "sectors": self.sectors,
            "failed_reasons": self.failed_reasons,
        }


class MarketRegimeService:
    def __init__(
        self,
        settings: AppSettings | None = None,
        market_data_service: Any | None = None,
        price_lookback_rows: int = DEFAULT_PRICE_LOOKBACK_ROWS,
    ) -> None:
        self.settings = settings or get_settings()
        # Optional: only used when ``fetch_missing=True`` to backfill regime
        # symbols (indexes/VIX/yield/sectors) that may not be in the watchlist.
        self.market_data_service = market_data_service
        self.price_lookback_rows = price_lookback_rows

    def ensure_tables(self, db: Session) -> None:
        ensure_tables(db)

    # ------------------------------------------------------------------ loaders
    def _load_closes(self, db: Session, symbol: str) -> tuple[list[float], date | None]:
        clean = symbol.strip().upper()
        rows = (
            db.query(DailyPrice)
            .filter(DailyPrice.symbol == clean)
            .order_by(DailyPrice.price_date.asc())
            .all()
        )
        if self.price_lookback_rows > 0:
            rows = rows[-self.price_lookback_rows :]

        closes = [float(r.close_price) for r in rows if r.close_price is not None]
        last_date = rows[-1].price_date if rows else None
        return closes, last_date

    # --------------------------------------------------------------- regime
    def compute_regime(self, db: Session) -> RegimeComputation:
        self.ensure_tables(db)

        s = self.settings
        index_symbols = list(s.market_regime_index_symbols)
        # Map by position so SPY/QQQ/IWM ordering in config drives the read; fall
        # back to the canonical symbols if the configured list is shorter.
        spy_symbol = index_symbols[0] if len(index_symbols) > 0 else "SPY"
        qqq_symbol = index_symbols[1] if len(index_symbols) > 1 else "QQQ"
        iwm_symbol = index_symbols[2] if len(index_symbols) > 2 else "IWM"

        spy_closes, spy_date = self._load_closes(db, spy_symbol)
        qqq_closes, qqq_date = self._load_closes(db, qqq_symbol)
        iwm_closes, iwm_date = self._load_closes(db, iwm_symbol)
        vix_closes, vix_date = self._load_closes(db, s.market_regime_vix_symbol)
        yield_closes, yield_date = self._load_closes(db, s.market_regime_yield_symbol)

        spy_trend = classify_trend(
            spy_closes,
            s.market_regime_trend_fast_period,
            s.market_regime_trend_slow_period,
            s.market_regime_min_price_rows,
        )
        qqq_trend = classify_trend(
            qqq_closes,
            s.market_regime_trend_fast_period,
            s.market_regime_trend_slow_period,
            s.market_regime_min_price_rows,
        )
        iwm_trend = classify_trend(
            iwm_closes,
            s.market_regime_trend_fast_period,
            s.market_regime_trend_slow_period,
            s.market_regime_min_price_rows,
        )

        vix_level = vix_closes[-1] if vix_closes else None
        vix_state = classify_vix(
            vix_level,
            s.market_regime_vix_calm_threshold,
            s.market_regime_vix_stress_threshold,
        )

        yield_result = classify_yield_pressure(
            yield_closes,
            s.market_regime_rs_lookback_days,
            s.market_regime_yield_pressure_level,
            s.market_regime_yield_rise_pct,
        )

        regime = composite_regime(
            spy_trend.trend,
            qqq_trend.trend,
            iwm_trend.trend,
            vix_state,
            yield_result.pressure,
        )

        # Snapshot date: prefer SPY's latest date, else the newest available.
        candidate_dates = [
            d for d in [spy_date, qqq_date, iwm_date, vix_date, yield_date] if d
        ]
        snapshot_date = spy_date or (max(candidate_dates) if candidate_dates else None)

        reasons: list[str] = []
        if spy_trend.trend == TREND_INSUFFICIENT and spy_trend.reason:
            reasons.append(f"{spy_symbol}: {spy_trend.reason}")
        if qqq_trend.trend == TREND_INSUFFICIENT and qqq_trend.reason:
            reasons.append(f"{qqq_symbol}: {qqq_trend.reason}")
        if iwm_trend.trend == TREND_INSUFFICIENT and iwm_trend.reason:
            reasons.append(f"{iwm_symbol}: {iwm_trend.reason}")
        if vix_state == VIX_UNKNOWN:
            reasons.append(f"{s.market_regime_vix_symbol}: no VIX level available.")
        if yield_result.reason:
            reasons.append(f"{s.market_regime_yield_symbol}: {yield_result.reason}")

        # SPY is the primary broad-market input. If it's missing the regime is
        # INSUFFICIENT (still non-blocking, still persisted). If SPY is present
        # but some secondary inputs are missing, the read is PARTIAL.
        if spy_trend.trend == TREND_INSUFFICIENT:
            status = INSUFFICIENT_PRICE_HISTORY
        elif reasons:
            status = PARTIAL
        else:
            status = SUFFICIENT

        return RegimeComputation(
            snapshot_date=snapshot_date,
            source_record_count=len(spy_closes),
            data_sufficiency_status=status,
            spy=spy_trend,
            qqq=qqq_trend,
            iwm=iwm_trend,
            vix_symbol=s.market_regime_vix_symbol,
            vix_level=vix_level,
            vix_state=vix_state,
            yield_symbol=s.market_regime_yield_symbol,
            yield_result=yield_result,
            regime_label=regime.regime_label,
            regime_score=regime.regime_score,
            uptrend_count=regime.uptrend_count,
            downtrend_count=regime.downtrend_count,
            regime_components=regime.components,
            insufficient_reasons=reasons,
            notes=None,
        )

    def persist_regime(
        self,
        db: Session,
        computation: RegimeComputation,
    ) -> tuple[MarketRegimeSnapshot, bool]:
        self.ensure_tables(db)

        if computation.snapshot_date is None:
            raise ValueError(
                "Cannot persist a market-regime snapshot with no snapshot_date "
                "(no price rows existed for any regime symbol)."
            )

        existing = (
            db.query(MarketRegimeSnapshot)
            .filter(MarketRegimeSnapshot.snapshot_date == computation.snapshot_date)
            .one_or_none()
        )

        values = {
            "source": "daily_prices",
            "source_record_count": computation.source_record_count,
            "spy_close": computation.spy.last_close,
            "qqq_close": computation.qqq.last_close,
            "iwm_close": computation.iwm.last_close,
            "spy_trend": computation.spy.trend,
            "qqq_trend": computation.qqq.trend,
            "iwm_trend": computation.iwm.trend,
            "index_uptrend_count": computation.uptrend_count,
            "index_downtrend_count": computation.downtrend_count,
            "vix_symbol": computation.vix_symbol,
            "vix_level": computation.vix_level,
            "vix_state": computation.vix_state,
            "yield_symbol": computation.yield_symbol,
            "yield_level": computation.yield_result.level,
            "yield_change_pct": computation.yield_result.change_pct,
            "yield_state": computation.yield_result.state,
            "yield_pressure": computation.yield_result.pressure,
            "regime_label": computation.regime_label,
            "regime_score": computation.regime_score,
            "data_sufficiency_status": computation.data_sufficiency_status,
            "insufficient_reasons_json": list(computation.insufficient_reasons),
            "notes": computation.notes,
        }

        if existing is None:
            row = MarketRegimeSnapshot(
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

    # -------------------------------------------------------------- sectors
    def compute_sector_strength(self, db: Session) -> list[SectorStrengthResult]:
        self.ensure_tables(db)

        s = self.settings
        lookback = s.market_regime_rs_lookback_days

        # Pre-load benchmark closes once.
        benchmark_closes: dict[str, list[float]] = {}
        for benchmark in s.market_regime_benchmark_symbols:
            benchmark_closes[benchmark], _ = self._load_closes(db, benchmark)

        results: list[SectorStrengthResult] = []
        # Rank within each benchmark group separately.
        for benchmark in s.market_regime_benchmark_symbols:
            group: list[SectorStrengthResult] = []
            for sector in s.market_regime_sector_etfs:
                sector_closes, _ = self._load_closes(db, sector)
                group.append(
                    compute_relative_strength(
                        sector_symbol=sector,
                        benchmark_symbol=benchmark,
                        sector_closes=sector_closes,
                        benchmark_closes=benchmark_closes.get(benchmark, []),
                        lookback_days=lookback,
                    )
                )
            results.extend(assign_ranks(group))

        return results

    def persist_sector(
        self,
        db: Session,
        result: SectorStrengthResult,
        snapshot_date: date,
    ) -> tuple[SectorStrengthSnapshot, bool]:
        self.ensure_tables(db)

        existing = (
            db.query(SectorStrengthSnapshot)
            .filter(SectorStrengthSnapshot.snapshot_date == snapshot_date)
            .filter(SectorStrengthSnapshot.sector_symbol == result.sector_symbol)
            .filter(SectorStrengthSnapshot.benchmark_symbol == result.benchmark_symbol)
            .one_or_none()
        )

        values = {
            "lookback_days": result.lookback_days,
            "source_record_count": result.sector_row_count,
            "sector_return_pct": result.sector_return_pct,
            "benchmark_return_pct": result.benchmark_return_pct,
            "relative_strength": result.relative_strength,
            "rs_rank": result.rs_rank,
            "trend": result.trend,
            "data_sufficiency_status": result.data_sufficiency_status,
            "insufficient_reasons_json": [result.reason] if result.reason else [],
            "notes": None,
        }

        if existing is None:
            row = SectorStrengthSnapshot(
                snapshot_date=snapshot_date,
                sector_symbol=result.sector_symbol,
                benchmark_symbol=result.benchmark_symbol,
                **values,
            )
            db.add(row)
            db.flush()
            return row, True

        for key, value in values.items():
            setattr(existing, key, value)
        db.flush()
        return existing, False

    # --------------------------------------------------------------- refresh
    def regime_symbols(self) -> list[str]:
        """All symbols this layer reads (indexes, VIX, yield, sector ETFs)."""
        s = self.settings
        ordered: list[str] = []
        for symbol in [
            *s.market_regime_index_symbols,
            s.market_regime_vix_symbol,
            s.market_regime_yield_symbol,
            *s.market_regime_benchmark_symbols,
            *s.market_regime_sector_etfs,
        ]:
            clean = symbol.strip().upper()
            if clean and clean not in ordered:
                ordered.append(clean)
        return ordered

    def refresh_market_regime(
        self,
        db: Session,
        fetch_missing: bool = False,
    ) -> MarketRegimeRefreshResult:
        self.ensure_tables(db)

        result = MarketRegimeRefreshResult()

        if fetch_missing and self.market_data_service is not None:
            try:
                fetch = self.market_data_service.refresh_market_data(
                    db=db,
                    symbols=self.regime_symbols(),
                    include_daily=True,
                    include_intraday=False,
                )
                result.fetched_symbols = list(
                    getattr(fetch, "successful_symbols", []) or []
                )
            except Exception as exc:  # non-blocking: stale/stored data still used
                result.failed_reasons["market_data_fetch"] = str(exc)

        computation = self.compute_regime(db)
        result.snapshot_date = computation.snapshot_date
        result.regime_label = computation.regime_label
        result.data_sufficiency_status = computation.data_sufficiency_status
        result.regime = computation.to_dict()

        # If no price rows existed for any regime symbol there is no date to key
        # the snapshot on -- return cleanly without inventing a row.
        if computation.snapshot_date is None:
            result.failed_reasons["market_regime"] = (
                "No daily price rows available for any regime symbol."
            )
            db.commit()
            return result

        _, inserted = self.persist_regime(db, computation)
        if inserted:
            result.regime_inserted += 1
        else:
            result.regime_updated += 1

        sector_results = self.compute_sector_strength(db)
        result.sector_count = len(sector_results)
        for sector_result in sector_results:
            result.sectors.append(sector_result.to_dict())
            _, sector_inserted = self.persist_sector(
                db, sector_result, computation.snapshot_date
            )
            if sector_inserted:
                result.sectors_inserted += 1
            else:
                result.sectors_updated += 1

        db.commit()
        return result


__all__ = [
    "DEFAULT_PRICE_LOOKBACK_ROWS",
    "INSUFFICIENT_PRICE_HISTORY",
    "PARTIAL",
    "SUFFICIENT",
    "MarketRegimeRefreshResult",
    "MarketRegimeService",
    "RegimeComputation",
]
