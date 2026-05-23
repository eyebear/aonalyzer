"""Phase 8 placeholder module.

Real option-chain collection is intentionally disabled for now because:
1. yfinance / Yahoo Options is currently blocked or rate-limited.
2. Tradier / Alpha Vantage / other reliable option-chain providers require API keys.
3. Fake option data is not acceptable for this project.

This placeholder keeps the Phase 8 module structure in place so later phases can
depend on stable imports, routes, and service names.

Future implementation should replace this file with a real provider-based option
chain collector.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

from app.common.service_utils import normalize_symbols


@dataclass(frozen=True)
class OptionContractRow:
    symbol: str
    expiration_date: date
    option_type: str
    contract_symbol: str | None
    strike: float | None
    bid: float | None
    ask: float | None
    last_price: float | None
    volume: int | None
    open_interest: int | None
    implied_volatility: float | None
    in_the_money: bool | None
    currency: str | None
    source: str = "placeholder"


@dataclass(frozen=True)
class NormalizedOptionSnapshot:
    symbol: str
    snapshot_time: datetime
    expiration_date: date
    dte: int
    option_type: str
    contract_symbol: str | None
    strike: float | None
    bid: float | None
    ask: float | None
    last_price: float | None
    volume: int | None
    open_interest: int | None
    implied_volatility: float | None
    in_the_money: bool | None
    currency: str | None
    mid_price: float | None
    spread_percent: float | None
    contract_cost: float | None
    breakeven: float | None
    source: str


@dataclass
class OptionChainRefreshResult:
    requested_symbols: list[str] = field(default_factory=list)
    successful_symbols: list[str] = field(default_factory=list)
    failed_symbols: list[str] = field(default_factory=list)

    expirations_processed: int = 0
    contracts_fetched: int = 0
    snapshots_inserted: int = 0
    quality_events_created: int = 0

    placeholder: bool = True
    message: str = (
        "Automatic option-chain collection is not enabled; it requires a "
        "supported market-data provider and API key. Paste option contract "
        "data manually to evaluate the option side."
    )

    failed_reasons: dict[str, str] = field(default_factory=dict)

    @property
    def records_created(self) -> int:
        return self.snapshots_inserted

    def to_dict(self) -> dict[str, Any]:
        return {
            "requested_symbols": self.requested_symbols,
            "successful_symbols": self.successful_symbols,
            "failed_symbols": self.failed_symbols,
            "expirations_processed": self.expirations_processed,
            "contracts_fetched": self.contracts_fetched,
            "snapshots_inserted": self.snapshots_inserted,
            "quality_events_created": self.quality_events_created,
            "records_created": self.records_created,
            "placeholder": self.placeholder,
            "message": self.message,
            "failed_reasons": self.failed_reasons,
        }


class YahooOptionChainClient:
    """
    Placeholder client.

    Kept only so imports and future provider replacement remain stable.
    """

    def fetch_expiration_dates(self, symbol: str) -> list[date]:
        return []

    def fetch_option_chain(
        self,
        symbol: str,
        expiration_date: date,
    ) -> list[OptionContractRow]:
        return []


class OptionChainService:
    """
    Placeholder service for Phase 8.

    This service intentionally does not fetch or store real option-chain data.
    It only keeps the application stable until a real provider is selected.
    """

    def __init__(
        self,
        client: YahooOptionChainClient | None = None,
    ) -> None:
        self.client = client or YahooOptionChainClient()

    def refresh_option_chains(
        self,
        db,
        symbols: list[str] | None = None,
        max_expirations: int = 4,
    ) -> OptionChainRefreshResult:
        selected_symbols = self._normalize_symbols(symbols or [])

        return OptionChainRefreshResult(
            requested_symbols=selected_symbols,
            successful_symbols=selected_symbols,
            failed_symbols=[],
            expirations_processed=0,
            contracts_fetched=0,
            snapshots_inserted=0,
            quality_events_created=0,
            placeholder=True,
            message=(
                "Automatic option-chain collection is not enabled; no option "
                "snapshots were fetched or stored. Paste option contract data "
                "manually to evaluate the option side."
            ),
        )

    def normalize_contract(
        self,
        contract: OptionContractRow,
    ) -> NormalizedOptionSnapshot:
        snapshot_time = datetime.now(timezone.utc)
        dte = max((contract.expiration_date - snapshot_time.date()).days, 0)

        mid_price = self.calculate_mid_price(
            bid=contract.bid,
            ask=contract.ask,
        )

        spread_percent = self.calculate_spread_percent(
            bid=contract.bid,
            ask=contract.ask,
            mid_price=mid_price,
        )

        contract_cost = self.calculate_contract_cost(mid_price)

        breakeven = self.calculate_breakeven(
            option_type=contract.option_type,
            strike=contract.strike,
            premium=mid_price,
        )

        return NormalizedOptionSnapshot(
            symbol=contract.symbol.upper(),
            snapshot_time=snapshot_time,
            expiration_date=contract.expiration_date,
            dte=dte,
            option_type=contract.option_type.upper(),
            contract_symbol=contract.contract_symbol,
            strike=contract.strike,
            bid=contract.bid,
            ask=contract.ask,
            last_price=contract.last_price,
            volume=contract.volume,
            open_interest=contract.open_interest,
            implied_volatility=contract.implied_volatility,
            in_the_money=contract.in_the_money,
            currency=contract.currency,
            mid_price=mid_price,
            spread_percent=spread_percent,
            contract_cost=contract_cost,
            breakeven=breakeven,
            source=contract.source,
        )

    def calculate_mid_price(
        self,
        bid: float | None,
        ask: float | None,
    ) -> float | None:
        if bid is None or ask is None:
            return None

        if bid < 0 or ask < 0:
            return None

        return (bid + ask) / 2

    def calculate_spread_percent(
        self,
        bid: float | None,
        ask: float | None,
        mid_price: float | None,
    ) -> float | None:
        if bid is None or ask is None or mid_price is None:
            return None

        if mid_price <= 0:
            return None

        return (ask - bid) / mid_price

    def calculate_contract_cost(
        self,
        premium: float | None,
    ) -> float | None:
        if premium is None:
            return None

        return premium * 100

    def calculate_breakeven(
        self,
        option_type: str,
        strike: float | None,
        premium: float | None,
    ) -> float | None:
        if strike is None or premium is None:
            return None

        normalized_type = option_type.upper()

        if normalized_type == "CALL":
            return strike + premium

        if normalized_type == "PUT":
            return strike - premium

        return None

    def ensure_option_chain_tables(self, db) -> None:
        """
        Placeholder.

        No option_chain_snapshots table is created in placeholder mode.
        A future real provider implementation should create/persist snapshots.
        """
        return None

    def load_watchlist_symbols(self, db) -> list[str]:
        """Intentional Phase 8 placeholder.

        Option-chain collection is non-blocking and not wired to the watchlist;
        this deliberately returns ``[]`` (it does NOT use the shared
        ``load_watchlist_symbols`` loader) so option work never drives or blocks
        stock-only analysis. Kept explicit rather than delegated.
        """
        return []

    def _normalize_symbols(self, symbols: list[str]) -> list[str]:
        return normalize_symbols(symbols)