from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.base import Base
from app.earnings.earnings_models import EarningsEvent, EarningsRiskSnapshot
from app.earnings.earnings_risk_service import (
    RISK_LABEL_EARNINGS_BEFORE_EXPIRATION,
    RISK_LABEL_EARNINGS_DATA_NOT_AVAILABLE,
    RISK_LABEL_EARNINGS_INSIDE_WINDOW,
    RISK_LABEL_NO_EARNINGS_NEAR,
    EarningsRiskService,
)
from app.options.manual_option_input_service import ManualOptionInputService


def create_test_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return engine, SessionLocal()


def _seed_earnings(db, symbol: str, when: datetime) -> None:
    db.add(
        EarningsEvent(
            symbol=symbol,
            earnings_datetime_utc=when,
            time_of_day="AMC",
            confirmed=True,
            source="test_source",
        )
    )
    db.commit()


def test_no_earnings_rows_yields_data_not_available_label() -> None:
    """Stock-only research must run even when we have no earnings rows."""
    _, db = create_test_session()
    service = EarningsRiskService(earnings_risk_window_days=7)

    computation = service.compute_for_symbol(
        db=db,
        symbol="AMD",
        now=datetime(2026, 5, 14, 12, 0, tzinfo=timezone.utc),
    )

    assert computation.risk_label == RISK_LABEL_EARNINGS_DATA_NOT_AVAILABLE
    assert computation.days_to_earnings is None
    assert computation.earnings_within_window is False
    assert computation.earnings_before_expiration == "NOT_APPLICABLE"
    assert computation.data_sufficiency_status == "EARNINGS_DATA_NOT_AVAILABLE"


def test_earnings_outside_window_yields_no_earnings_near_label() -> None:
    _, db = create_test_session()
    now = datetime(2026, 5, 14, 12, 0, tzinfo=timezone.utc)

    _seed_earnings(db, "AMD", now + timedelta(days=45))

    service = EarningsRiskService(earnings_risk_window_days=7)
    computation = service.compute_for_symbol(db=db, symbol="AMD", now=now)

    assert computation.risk_label == RISK_LABEL_NO_EARNINGS_NEAR
    assert computation.days_to_earnings == 45
    assert computation.earnings_within_window is False


def test_earnings_inside_window_without_option_yields_inside_window_label() -> None:
    _, db = create_test_session()
    now = datetime(2026, 5, 14, 12, 0, tzinfo=timezone.utc)

    _seed_earnings(db, "AMD", now + timedelta(days=3))

    service = EarningsRiskService(earnings_risk_window_days=7)
    computation = service.compute_for_symbol(db=db, symbol="AMD", now=now)

    assert computation.risk_label == RISK_LABEL_EARNINGS_INSIDE_WINDOW
    assert computation.days_to_earnings == 3
    assert computation.earnings_within_window is True
    assert computation.earnings_before_expiration == "NOT_APPLICABLE"


def test_earnings_before_expiration_label_when_option_exists() -> None:
    _, db = create_test_session()
    now = datetime(2026, 5, 14, 12, 0, tzinfo=timezone.utc)

    _seed_earnings(db, "AMD", now + timedelta(days=5))

    option_service = ManualOptionInputService()
    option_service.create_manual_snapshot(
        db=db,
        raw_text="AMD June 19 2026 170 call bid 8.20 ask 8.80",
        symbol="AMD",
    )

    service = EarningsRiskService(earnings_risk_window_days=7)
    computation = service.compute_for_symbol(db=db, symbol="AMD", now=now)

    assert computation.risk_label == RISK_LABEL_EARNINGS_BEFORE_EXPIRATION
    assert computation.earnings_before_expiration == "TRUE"
    assert computation.manual_option_expiration_date.isoformat() == "2026-06-19"


def test_refresh_persists_snapshot_and_updates_on_rerun() -> None:
    _, db = create_test_session()
    now = datetime(2026, 5, 14, 12, 0, tzinfo=timezone.utc)
    _seed_earnings(db, "AMD", now + timedelta(days=3))

    service = EarningsRiskService(earnings_risk_window_days=7)

    first = service.refresh_earnings_risk(db=db, symbols=["AMD"], now=now)
    second = service.refresh_earnings_risk(db=db, symbols=["AMD"], now=now)

    assert first.snapshots_inserted == 1
    assert second.snapshots_inserted == 0
    assert second.snapshots_updated == 1
    assert db.query(EarningsRiskSnapshot).count() == 1


def test_refresh_writes_snapshot_even_when_data_not_available() -> None:
    """Stock-only research: writing the no-data snapshot is the right behavior
    so the dashboard can show ``EARNINGS_DATA_NOT_AVAILABLE`` cleanly."""
    _, db = create_test_session()
    service = EarningsRiskService(earnings_risk_window_days=7)

    now = datetime(2026, 5, 14, 12, 0, tzinfo=timezone.utc)
    result = service.refresh_earnings_risk(db=db, symbols=["AMD"], now=now)

    assert "AMD" in result.no_data_symbols
    assert db.query(EarningsRiskSnapshot).count() == 1
    row = db.query(EarningsRiskSnapshot).one()
    assert row.risk_label == RISK_LABEL_EARNINGS_DATA_NOT_AVAILABLE
    assert row.data_sufficiency_status == "EARNINGS_DATA_NOT_AVAILABLE"


def test_refresh_works_with_no_option_tables_present() -> None:
    """Manual option table is created lazily; Phase 10 must not depend on it."""
    _, db = create_test_session()
    now = datetime(2026, 5, 14, 12, 0, tzinfo=timezone.utc)
    _seed_earnings(db, "AMD", now + timedelta(days=3))

    # Confirm manual_option_snapshots is NOT in this DB.
    from sqlalchemy import inspect

    inspector = inspect(db.get_bind())
    assert "manual_option_snapshots" not in inspector.get_table_names()

    service = EarningsRiskService(earnings_risk_window_days=7)
    computation = service.compute_for_symbol(db=db, symbol="AMD", now=now)

    assert computation.risk_label == RISK_LABEL_EARNINGS_INSIDE_WINDOW
    assert computation.earnings_before_expiration == "NOT_APPLICABLE"
