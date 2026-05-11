from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any


EXPECTED_OPTION_FIELDS = [
    "symbol",
    "underlying_price",
    "expiration_date",
    "option_type",
    "strike",
    "bid",
    "ask",
    "last_price",
    "volume",
    "open_interest",
    "implied_volatility",
    "delta",
    "gamma",
    "theta",
    "vega",
    "rho",
    "source_name",
]


@dataclass(frozen=True)
class ParsedManualOptionInput:
    raw_text: str

    symbol: str | None = None
    source_name: str | None = None

    underlying_price: float | None = None
    expiration_date: date | None = None
    option_type: str | None = None
    strike: float | None = None

    bid: float | None = None
    ask: float | None = None
    last_price: float | None = None

    volume: int | None = None
    open_interest: int | None = None

    implied_volatility: float | None = None
    delta: float | None = None
    gamma: float | None = None
    theta: float | None = None
    vega: float | None = None
    rho: float | None = None

    dte: int | None = None
    mid_price: float | None = None
    spread_percent: float | None = None
    contract_cost: float | None = None
    breakeven: float | None = None
    breakeven_distance: float | None = None
    breakeven_distance_percent: float | None = None

    parser_confidence: str = "LOW"
    missing_fields: list[str] = field(default_factory=list)
    parsed_fields: dict[str, Any] = field(default_factory=dict)
    data_quality_status: str = "INSUFFICIENT_OPTION_DATA"
    needs_ai_review: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw_text": self.raw_text,
            "symbol": self.symbol,
            "source_name": self.source_name,
            "underlying_price": self.underlying_price,
            "expiration_date": self.expiration_date.isoformat()
            if self.expiration_date
            else None,
            "option_type": self.option_type,
            "strike": self.strike,
            "bid": self.bid,
            "ask": self.ask,
            "last_price": self.last_price,
            "volume": self.volume,
            "open_interest": self.open_interest,
            "implied_volatility": self.implied_volatility,
            "delta": self.delta,
            "gamma": self.gamma,
            "theta": self.theta,
            "vega": self.vega,
            "rho": self.rho,
            "dte": self.dte,
            "mid_price": self.mid_price,
            "spread_percent": self.spread_percent,
            "contract_cost": self.contract_cost,
            "breakeven": self.breakeven,
            "breakeven_distance": self.breakeven_distance,
            "breakeven_distance_percent": self.breakeven_distance_percent,
            "parser_confidence": self.parser_confidence,
            "missing_fields": self.missing_fields,
            "parsed_fields": self.parsed_fields,
            "data_quality_status": self.data_quality_status,
            "needs_ai_review": self.needs_ai_review,
        }


@dataclass(frozen=True)
class ManualOptionSnapshotRecord:
    id: int
    raw_text: str

    symbol: str | None
    source_name: str | None

    underlying_price: float | None
    expiration_date: date | None
    option_type: str | None
    strike: float | None

    bid: float | None
    ask: float | None
    last_price: float | None

    volume: int | None
    open_interest: int | None

    implied_volatility: float | None
    delta: float | None
    gamma: float | None
    theta: float | None
    vega: float | None
    rho: float | None

    dte: int | None
    mid_price: float | None
    spread_percent: float | None
    contract_cost: float | None
    breakeven: float | None
    breakeven_distance: float | None
    breakeven_distance_percent: float | None

    parser_confidence: str
    missing_fields: list[str]
    parsed_fields: dict[str, Any]
    data_quality_status: str

    ai_status: str | None
    ai_summary: str | None
    ai_analysis_json: dict[str, Any] | None

    created_at: datetime | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "raw_text": self.raw_text,
            "symbol": self.symbol,
            "source_name": self.source_name,
            "underlying_price": self.underlying_price,
            "expiration_date": self.expiration_date.isoformat()
            if self.expiration_date
            else None,
            "option_type": self.option_type,
            "strike": self.strike,
            "bid": self.bid,
            "ask": self.ask,
            "last_price": self.last_price,
            "volume": self.volume,
            "open_interest": self.open_interest,
            "implied_volatility": self.implied_volatility,
            "delta": self.delta,
            "gamma": self.gamma,
            "theta": self.theta,
            "vega": self.vega,
            "rho": self.rho,
            "dte": self.dte,
            "mid_price": self.mid_price,
            "spread_percent": self.spread_percent,
            "contract_cost": self.contract_cost,
            "breakeven": self.breakeven,
            "breakeven_distance": self.breakeven_distance,
            "breakeven_distance_percent": self.breakeven_distance_percent,
            "parser_confidence": self.parser_confidence,
            "missing_fields": self.missing_fields,
            "parsed_fields": self.parsed_fields,
            "data_quality_status": self.data_quality_status,
            "ai_status": self.ai_status,
            "ai_summary": self.ai_summary,
            "ai_analysis": self.ai_analysis_json,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }