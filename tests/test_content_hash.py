from datetime import datetime, timezone

from app.event_normalizer.content_hash import (
    build_content_hash,
    normalize_headline,
    normalize_source_url,
)


def test_normalize_headline_collapses_whitespace_and_lowercases() -> None:
    assert normalize_headline("   AMD   Beats  EARNINGS  ") == "amd beats earnings"
    assert normalize_headline(None) == ""


def test_normalize_source_url_strips_and_lowercases() -> None:
    assert (
        normalize_source_url("  HTTPS://Example.COM/path?x=1  ")
        == "https://example.com/path?x=1"
    )
    assert normalize_source_url(None) == ""


def test_same_inputs_produce_same_hash() -> None:
    hash_a = build_content_hash(
        event_type="NEWS",
        source="google_news",
        headline="AMD beats earnings",
        symbol="AMD",
        source_url="https://example.com/a",
    )
    hash_b = build_content_hash(
        event_type="NEWS",
        source="google_news",
        headline="AMD beats earnings",
        symbol="AMD",
        source_url="https://example.com/a",
    )

    assert hash_a == hash_b


def test_different_symbols_produce_different_hashes_for_multi_ticker_news() -> None:
    hash_amd = build_content_hash(
        event_type="NEWS",
        source="google_news",
        headline="Chipmakers rally on AI demand",
        symbol="AMD",
        source_url="https://example.com/rally",
    )
    hash_nvda = build_content_hash(
        event_type="NEWS",
        source="google_news",
        headline="Chipmakers rally on AI demand",
        symbol="NVDA",
        source_url="https://example.com/rally",
    )

    assert hash_amd != hash_nvda


def test_event_time_is_not_part_of_hash_so_minor_time_drift_dedupes() -> None:
    hash_with_time = build_content_hash(
        event_type="NEWS",
        source="google_news",
        headline="AMD beats earnings",
        symbol="AMD",
        source_url="https://example.com/a",
        event_time=datetime(2026, 5, 14, 12, 0, tzinfo=timezone.utc),
    )
    hash_without_time = build_content_hash(
        event_type="NEWS",
        source="google_news",
        headline="AMD beats earnings",
        symbol="AMD",
        source_url="https://example.com/a",
        event_time=None,
    )

    assert hash_with_time == hash_without_time


def test_whitespace_variants_dedupe() -> None:
    hash_normal = build_content_hash(
        event_type="NEWS",
        source="google_news",
        headline="AMD beats earnings",
        symbol="AMD",
        source_url="https://example.com/a",
    )
    hash_messy = build_content_hash(
        event_type="news",
        source="GOOGLE_NEWS",
        headline="  AMD   Beats   Earnings  ",
        symbol="amd",
        source_url="HTTPS://Example.com/a",
    )

    assert hash_normal == hash_messy
