from app.options.manual_option_parser import ManualOptionTextParser


def test_parser_extracts_messy_manual_option_text() -> None:
    parser = ManualOptionTextParser()

    raw_text = (
        "AMD June 19 2026 170 call, stock around 165.20, "
        "bid 8.20 ask 8.80, last 8.50, IV around 42.5%, "
        "delta .48, gamma .025, theta -.09, vega .31, "
        "volume 1200, OI 5400."
    )

    result = parser.parse(raw_text)

    assert result.symbol == "AMD"
    assert result.expiration_date is not None
    assert result.expiration_date.isoformat() == "2026-06-19"
    assert result.option_type == "CALL"
    assert result.strike == 170.0
    assert result.underlying_price == 165.20
    assert result.bid == 8.20
    assert result.ask == 8.80
    assert result.last_price == 8.50
    assert result.volume == 1200
    assert result.open_interest == 5400
    assert result.implied_volatility == 0.425
    assert result.delta == 0.48
    assert result.gamma == 0.025
    assert result.theta == -0.09
    assert result.vega == 0.31

    assert result.mid_price == 8.5
    assert round(result.spread_percent or 0, 6) == round(0.60 / 8.5, 6)
    assert result.contract_cost == 850.0
    assert result.breakeven == 178.5
    assert round(result.breakeven_distance or 0, 6) == round(178.5 - 165.2, 6)
    assert result.parser_confidence == "HIGH"
    assert result.data_quality_status == "OPTION_TEXT_PARSED"


def test_parser_accepts_supplied_symbol() -> None:
    parser = ManualOptionTextParser()

    result = parser.parse(
        raw_text="June 19 2026 170 call bid 8.20 ask 8.80",
        supplied_symbol="amd",
    )

    assert result.symbol == "AMD"
    assert result.option_type == "CALL"
    assert result.strike == 170.0
    assert result.bid == 8.20
    assert result.ask == 8.80


def test_parser_does_not_invent_missing_values() -> None:
    parser = ManualOptionTextParser()

    result = parser.parse(
        raw_text="I am looking at an AMD option but I do not have the chain data yet.",
    )

    assert result.symbol == "AMD"
    assert result.expiration_date is None
    assert result.option_type is None
    assert result.strike is None
    assert result.bid is None
    assert result.ask is None
    assert result.mid_price is None
    assert result.contract_cost is None
    assert "expiration_date" in result.missing_fields
    assert result.data_quality_status == "INSUFFICIENT_OPTION_DATA"


def test_parser_handles_compact_option_row_text() -> None:
    parser = ManualOptionTextParser()

    result = parser.parse(
        raw_text=(
            "AMD 06/19/26 C170 8.20 x 8.80 last 8.50 "
            "vol 1200 OI 5400 IV 42.5 delta .48 theta -.09"
        )
    )

    assert result.symbol == "AMD"
    assert result.expiration_date is not None
    assert result.expiration_date.isoformat() == "2026-06-19"
    assert result.option_type == "CALL"
    assert result.strike == 170.0
    assert result.bid == 8.20
    assert result.ask == 8.80
    assert result.last_price == 8.50
    assert result.volume == 1200
    assert result.open_interest == 5400
    assert result.implied_volatility == 0.425
    assert result.delta == 0.48
    assert result.theta == -0.09