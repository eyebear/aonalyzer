from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass(frozen=True)
class IndicatorValues:
    last_close: float | None
    last_volume: float | None

    sma_20: float | None
    sma_50: float | None
    sma_200: float | None

    ema_12: float | None
    ema_26: float | None

    rsi_14: float | None

    macd: float | None
    macd_signal: float | None
    macd_histogram: float | None

    atr_14: float | None

    bollinger_upper: float | None
    bollinger_middle: float | None
    bollinger_lower: float | None

    volume_ratio_20: float | None

    insufficient_indicators: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "last_close": self.last_close,
            "last_volume": self.last_volume,
            "sma_20": self.sma_20,
            "sma_50": self.sma_50,
            "sma_200": self.sma_200,
            "ema_12": self.ema_12,
            "ema_26": self.ema_26,
            "rsi_14": self.rsi_14,
            "macd": self.macd,
            "macd_signal": self.macd_signal,
            "macd_histogram": self.macd_histogram,
            "atr_14": self.atr_14,
            "bollinger_upper": self.bollinger_upper,
            "bollinger_middle": self.bollinger_middle,
            "bollinger_lower": self.bollinger_lower,
            "volume_ratio_20": self.volume_ratio_20,
            "insufficient_indicators": list(self.insufficient_indicators),
        }


@dataclass(frozen=True)
class SnapshotComputeResult:
    symbol: str
    snapshot_date: date | None
    source_record_count: int
    data_sufficiency_status: str
    indicators: IndicatorValues | None
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "snapshot_date": self.snapshot_date.isoformat()
            if self.snapshot_date is not None
            else None,
            "source_record_count": self.source_record_count,
            "data_sufficiency_status": self.data_sufficiency_status,
            "indicators": self.indicators.to_dict() if self.indicators else None,
            "reason": self.reason,
        }


@dataclass
class TechnicalRefreshResult:
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


__all__ = [
    "IndicatorValues",
    "SnapshotComputeResult",
    "TechnicalRefreshResult",
]
