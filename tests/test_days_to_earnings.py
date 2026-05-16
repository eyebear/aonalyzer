from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.base import Base
from app.earnings.days_to_earnings_calculator import calculate_days_to_earnings
from app.earnings.earnings_models import EarningsEvent


def create_test_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return engine, SessionLocal()


def test_returns_none_when_no_earnings_rows() -> None:
    _, db = create_test_session()

    now = datetime(2026, 5, 14, 12, 0, tzinfo=timezone.utc)
    result = calculate_days_to_earnings(db=db, symbol="AMD", now=now)

    assert result.found_future_earnings is False
    assert result.days_to_earnings is None
    assert result.next_earnings_datetime_utc is None


def test_picks_soonest_future_earnings() -> None:
    _, db = create_test_session()

    now = datetime(2026, 5, 14, 12, 0, tzinfo=timezone.utc)

    db.add(
        EarningsEvent(
            symbol="AMD",
            earnings_datetime_utc=now - timedelta(days=30),
            time_of_day="AMC",
            confirmed=True,
            source="test_source",
        )
    )
    db.add(
        EarningsEvent(
            symbol="AMD",
            earnings_datetime_utc=now + timedelta(days=7),
            time_of_day="BMO",
            confirmed=False,
            source="test_source",
        )
    )
    db.add(
        EarningsEvent(
            symbol="AMD",
            earnings_datetime_utc=now + timedelta(days=90),
            time_of_day="AMC",
            confirmed=False,
            source="test_source",
        )
    )
    db.commit()

    result = calculate_days_to_earnings(db=db, symbol="AMD", now=now)

    assert result.found_future_earnings is True
    assert result.days_to_earnings == 7
    assert result.next_earnings_datetime_utc is not None


def test_returns_zero_when_earnings_is_today() -> None:
    _, db = create_test_session()

    now = datetime(2026, 5, 14, 12, 0, tzinfo=timezone.utc)
    db.add(
        EarningsEvent(
            symbol="AMD",
            earnings_datetime_utc=now + timedelta(hours=3),
            time_of_day="AMC",
            source="test_source",
        )
    )
    db.commit()

    result = calculate_days_to_earnings(db=db, symbol="AMD", now=now)

    assert result.days_to_earnings == 0


def test_ignores_past_only_history() -> None:
    _, db = create_test_session()

    now = datetime(2026, 5, 14, 12, 0, tzinfo=timezone.utc)
    db.add(
        EarningsEvent(
            symbol="AMD",
            earnings_datetime_utc=now - timedelta(days=5),
            source="test_source",
        )
    )
    db.commit()

    result = calculate_days_to_earnings(db=db, symbol="AMD", now=now)

    assert result.found_future_earnings is False
    assert result.days_to_earnings is None
