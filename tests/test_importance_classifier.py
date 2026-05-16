from datetime import datetime, timedelta, timezone

from app.event_normalizer.event_labels import ImportanceLevel
from app.event_normalizer.importance_classifier import ImportanceClassifier


def test_news_with_high_keyword_is_high() -> None:
    classifier = ImportanceClassifier()
    verdict = classifier.classify(
        event_type="NEWS",
        headline="AMD reports record earnings",
        source="google_news",
        event_time=None,
    )

    assert verdict.level == ImportanceLevel.HIGH
    assert "earnings" in verdict.reason


def test_news_with_medium_keyword_is_medium() -> None:
    classifier = ImportanceClassifier()
    verdict = classifier.classify(
        event_type="NEWS",
        headline="Analyst raises price target on NVDA",
        source="google_news",
        event_time=None,
    )

    assert verdict.level == ImportanceLevel.MEDIUM


def test_news_without_keywords_is_low() -> None:
    classifier = ImportanceClassifier()
    verdict = classifier.classify(
        event_type="NEWS",
        headline="AMD logo redesign sparks design debate",
        source="some_blog",
        event_time=None,
    )

    assert verdict.level == ImportanceLevel.LOW


def test_filing_type_8k_is_high() -> None:
    classifier = ImportanceClassifier()
    verdict = classifier.classify(
        event_type="FILING",
        headline="AMD 8-K material event",
        source="sec_edgar",
        filing_type="8-K",
        event_time=None,
    )

    assert verdict.level == ImportanceLevel.HIGH


def test_other_filing_is_medium() -> None:
    classifier = ImportanceClassifier()
    verdict = classifier.classify(
        event_type="FILING",
        headline="Some misc filing",
        source="sec_edgar",
        filing_type="SC 13D/A",
        event_time=None,
    )

    assert verdict.level == ImportanceLevel.MEDIUM


def test_macro_with_fomc_keyword_is_high() -> None:
    classifier = ImportanceClassifier()
    verdict = classifier.classify(
        event_type="MACRO",
        headline="FOMC raises rates by 25bps",
        source="federal_reserve",
        event_time=None,
    )

    assert verdict.level == ImportanceLevel.HIGH


def test_trusted_source_lifts_low_to_medium() -> None:
    classifier = ImportanceClassifier()
    verdict = classifier.classify(
        event_type="NEWS",
        headline="Boring market color piece",
        source="Reuters Wire",
        event_time=None,
    )

    assert verdict.level == ImportanceLevel.MEDIUM


def test_stale_event_demotes_high_to_medium() -> None:
    classifier = ImportanceClassifier()
    now = datetime(2026, 5, 14, 12, 0, tzinfo=timezone.utc)

    verdict = classifier.classify(
        event_type="NEWS",
        headline="AMD reports record earnings",
        source="google_news",
        event_time=now - timedelta(days=30),
        now=now,
    )

    assert verdict.level == ImportanceLevel.MEDIUM
    assert "older" in verdict.reason


def test_very_recent_event_boosts_medium_to_high() -> None:
    classifier = ImportanceClassifier()
    now = datetime(2026, 5, 14, 12, 0, tzinfo=timezone.utc)

    verdict = classifier.classify(
        event_type="NEWS",
        headline="Analyst raises price target on NVDA",
        source="google_news",
        event_time=now - timedelta(hours=1),
        now=now,
    )

    assert verdict.level == ImportanceLevel.HIGH
