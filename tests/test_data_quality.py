from datetime import datetime, timedelta, timezone

from app.data_quality.data_quality_checker import (
    DataFreshnessChecker,
    DataQualityChecker,
)
from app.data_quality.data_sufficiency_labels import DataSufficiencyLabel


def test_missing_option_data_produces_insufficient_option_data() -> None:
    checker = DataQualityChecker()

    result = checker.check_option_data(option_rows=[], symbol="AMD")

    assert result.label == DataSufficiencyLabel.INSUFFICIENT_OPTION_DATA
    assert result.data_category == "option_chain"
    assert result.symbol == "AMD"


def test_missing_price_history_produces_insufficient_price_history() -> None:
    checker = DataQualityChecker()

    result = checker.check_price_history(price_rows=[], symbol="AMD")

    assert result.label == DataSufficiencyLabel.INSUFFICIENT_PRICE_HISTORY
    assert result.data_category == "price_history"
    assert result.symbol == "AMD"


def test_data_freshness_status_is_available_for_missing_data() -> None:
    checker = DataFreshnessChecker()

    result = checker.check_freshness(
        data_category="option_chain",
        latest_success_at=None,
    )

    assert result["data_category"] == "option_chain"
    assert result["freshness_status"] == "MISSING"
    assert result["is_available"] is False
    assert "reason" in result


def test_data_freshness_status_is_fresh_when_recent() -> None:
    checker = DataFreshnessChecker()

    now = datetime.now(timezone.utc)

    result = checker.check_freshness(
        data_category="market_data",
        latest_success_at=now - timedelta(minutes=5),
        now=now,
        max_age_minutes=30,
    )

    assert result["data_category"] == "market_data"
    assert result["freshness_status"] == "FRESH"
    assert result["is_available"] is True


def test_data_freshness_status_is_stale_when_too_old() -> None:
    checker = DataFreshnessChecker()

    now = datetime.now(timezone.utc)

    result = checker.check_freshness(
        data_category="market_data",
        latest_success_at=now - timedelta(minutes=120),
        now=now,
        max_age_minutes=30,
    )

    assert result["data_category"] == "market_data"
    assert result["freshness_status"] == "STALE"
    assert result["is_available"] is False


def test_missing_iv_data_produces_insufficient_iv_data() -> None:
    checker = DataQualityChecker()

    option_rows = [
        {
            "bid": 1.2,
            "ask": 1.4,
            "open_interest": 100,
            "implied_volatility": None,
        }
    ]

    result = checker.check_iv_data(option_rows=option_rows, symbol="AMD")

    assert result.label == DataSufficiencyLabel.INSUFFICIENT_IV_DATA
    assert result.data_category == "iv_data"
    assert result.symbol == "AMD"


def test_invalid_news_data_produces_insufficient_news_data() -> None:
    checker = DataQualityChecker()

    news_rows = [
        {
            "source": "Yahoo Finance",
            "title": None,
            "event_time": "2026-05-11T12:00:00Z",
        }
    ]

    result = checker.check_news_data(news_rows=news_rows, symbol="AMD")

    assert result.label == DataSufficiencyLabel.INSUFFICIENT_NEWS_DATA
    assert result.data_category == "news"
    assert result.symbol == "AMD"


def test_valid_option_data_is_sufficient() -> None:
    checker = DataQualityChecker()

    option_rows = [
        {
            "bid": 1.2,
            "ask": 1.4,
            "open_interest": 100,
            "implied_volatility": 0.45,
        }
    ]

    result = checker.check_option_data(option_rows=option_rows, symbol="AMD")

    assert result.label == DataSufficiencyLabel.SUFFICIENT
    assert result.data_category == "option_chain"
    assert result.symbol == "AMD"