from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.base import Base
from app.earnings.earnings_before_expiration_checker import (
    EARNINGS_BEFORE_EXPIRATION_FALSE,
    EARNINGS_BEFORE_EXPIRATION_NOT_APPLICABLE,
    EARNINGS_BEFORE_EXPIRATION_TRUE,
    check_earnings_before_expiration,
)
from app.options.manual_option_input_service import ManualOptionInputService


def create_test_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return engine, SessionLocal()


def test_returns_not_applicable_when_no_earnings_datetime() -> None:
    _, db = create_test_session()

    result = check_earnings_before_expiration(
        db=db,
        symbol="AMD",
        next_earnings_datetime_utc=None,
    )

    assert result.status == EARNINGS_BEFORE_EXPIRATION_NOT_APPLICABLE
    assert "No future earnings" in result.reason


def test_returns_not_applicable_when_no_manual_option_table() -> None:
    """Phase 10 independence: stock-only research must work without options."""
    _, db = create_test_session()

    # manual_option_snapshots table is NOT created here (lazy-creation owned by
    # ManualOptionInputService.ensure_manual_option_tables, never invoked).
    earnings_at = datetime(2026, 6, 1, 20, 0, tzinfo=timezone.utc)
    result = check_earnings_before_expiration(
        db=db,
        symbol="AMD",
        next_earnings_datetime_utc=earnings_at,
    )

    assert result.status == EARNINGS_BEFORE_EXPIRATION_NOT_APPLICABLE
    assert result.option_expiration_date is None
    assert "No manual option snapshot" in result.reason


def test_returns_not_applicable_when_manual_option_has_no_expiration() -> None:
    _, db = create_test_session()
    service = ManualOptionInputService()

    # A note that doesn't include an expiration date.
    service.create_manual_snapshot(
        db=db,
        raw_text="AMD option idea but no expiration parsed.",
        symbol="AMD",
    )

    earnings_at = datetime(2026, 6, 1, 20, 0, tzinfo=timezone.utc)
    result = check_earnings_before_expiration(
        db=db,
        symbol="AMD",
        next_earnings_datetime_utc=earnings_at,
    )

    assert result.status == EARNINGS_BEFORE_EXPIRATION_NOT_APPLICABLE
    assert result.option_expiration_date is None


def test_true_when_earnings_before_option_expiration() -> None:
    _, db = create_test_session()
    service = ManualOptionInputService()

    # Manual option with expiration 2026-06-19; earnings on 2026-06-10 → TRUE.
    service.create_manual_snapshot(
        db=db,
        raw_text="AMD June 19 2026 170 call bid 8.20 ask 8.80",
        symbol="AMD",
    )

    earnings_at = datetime(2026, 6, 10, 20, 0, tzinfo=timezone.utc)
    result = check_earnings_before_expiration(
        db=db,
        symbol="AMD",
        next_earnings_datetime_utc=earnings_at,
    )

    assert result.status == EARNINGS_BEFORE_EXPIRATION_TRUE
    assert result.option_expiration_date.isoformat() == "2026-06-19"


def test_false_when_earnings_after_option_expiration() -> None:
    _, db = create_test_session()
    service = ManualOptionInputService()

    service.create_manual_snapshot(
        db=db,
        raw_text="AMD June 19 2026 170 call bid 8.20 ask 8.80",
        symbol="AMD",
    )

    earnings_at = datetime(2026, 7, 10, 20, 0, tzinfo=timezone.utc)
    result = check_earnings_before_expiration(
        db=db,
        symbol="AMD",
        next_earnings_datetime_utc=earnings_at,
    )

    assert result.status == EARNINGS_BEFORE_EXPIRATION_FALSE
    assert result.option_expiration_date.isoformat() == "2026-06-19"
