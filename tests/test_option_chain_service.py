from datetime import date

from app.options.option_chain_service import (
    OptionChainService,
    OptionContractRow,
)


def test_phase_8_placeholder_refresh_returns_successful_placeholder_result() -> None:
    service = OptionChainService()

    result = service.refresh_option_chains(
        db=None,
        symbols=["SPY"],
        max_expirations=1,
    )

    assert result.placeholder is True
    assert result.requested_symbols == ["SPY"]
    assert result.successful_symbols == ["SPY"]
    assert result.records_created == 0
    assert "placeholder" in result.message.lower()


def test_option_calculations_are_kept_for_future_real_provider() -> None:
    service = OptionChainService()

    call_contract = OptionContractRow(
        symbol="SPY",
        expiration_date=date(2026, 6, 19),
        option_type="CALL",
        contract_symbol="SPY260619C00750000",
        strike=750.0,
        bid=10.0,
        ask=12.0,
        last_price=11.0,
        volume=100,
        open_interest=500,
        implied_volatility=0.25,
        in_the_money=False,
        currency="USD",
        source="placeholder",
    )

    put_contract = OptionContractRow(
        symbol="SPY",
        expiration_date=date(2026, 6, 19),
        option_type="PUT",
        contract_symbol="SPY260619P00700000",
        strike=700.0,
        bid=8.0,
        ask=10.0,
        last_price=9.0,
        volume=90,
        open_interest=400,
        implied_volatility=0.30,
        in_the_money=False,
        currency="USD",
        source="placeholder",
    )

    normalized_call = service.normalize_contract(call_contract)
    normalized_put = service.normalize_contract(put_contract)

    assert normalized_call.mid_price == 11.0
    assert round(normalized_call.spread_percent, 6) == round(2.0 / 11.0, 6)
    assert normalized_call.contract_cost == 1100.0
    assert normalized_call.breakeven == 761.0

    assert normalized_put.mid_price == 9.0
    assert round(normalized_put.spread_percent, 6) == round(2.0 / 9.0, 6)
    assert normalized_put.contract_cost == 900.0
    assert normalized_put.breakeven == 691.0