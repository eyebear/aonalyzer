from datetime import date, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.base import Base
from app.iv_history.iv_models import IvHistoryDay, IvRiskSnapshot
from app.iv_history.iv_risk_service import (
    RISK_LABEL_INSUFFICIENT_IV_HISTORY,
    RISK_LABEL_IV_DATA_NOT_AVAILABLE,
    RISK_LABEL_IV_LOW,
    RISK_LABEL_IV_REJECT,
    RISK_LABEL_IV_WARNING,
    IvRiskService,
)


def create_test_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return engine, SessionLocal()


def _seed_iv_history(db, symbol: str, values: list[float], start: date) -> None:
    for i, value in enumerate(values):
        db.add(
            IvHistoryDay(
                symbol=symbol,
                snapshot_date=start + timedelta(days=i),
                atm_iv_30d=value,
                source="test",
            )
        )
    db.commit()


def test_no_history_yields_iv_data_not_available() -> None:
    """Phase 10 rule: missing IV must surface as IV_DATA_NOT_AVAILABLE,
    never a fabricated rank/percentile."""
    _, db = create_test_session()

    service = IvRiskService(
        minimum_history_days=30,
        iv_warning_threshold=70.0,
        iv_reject_threshold=85.0,
    )
    computation = service.compute_for_symbol(db=db, symbol="AMD")

    assert computation.risk_label == RISK_LABEL_IV_DATA_NOT_AVAILABLE
    assert computation.iv_rank is None
    assert computation.iv_percentile is None
    assert computation.iv_history_days_used == 0
    assert computation.data_sufficiency_status == "IV_DATA_NOT_AVAILABLE"


def test_too_little_history_yields_insufficient_iv_history() -> None:
    _, db = create_test_session()

    # 20 rows: below the 30-row minimum.
    _seed_iv_history(db, "AMD", [0.25 + i * 0.001 for i in range(20)], date(2026, 4, 1))

    service = IvRiskService(
        minimum_history_days=30,
        iv_warning_threshold=70.0,
        iv_reject_threshold=85.0,
    )
    computation = service.compute_for_symbol(db=db, symbol="AMD")

    assert computation.risk_label == RISK_LABEL_INSUFFICIENT_IV_HISTORY
    assert computation.iv_rank is None
    assert computation.iv_percentile is None
    assert computation.iv_history_days_used == 20
    assert computation.data_sufficiency_status == "INSUFFICIENT_IV_HISTORY"


def test_iv_low_when_rank_below_warning_threshold() -> None:
    _, db = create_test_session()

    # History 0.10..0.30 (40 rows), current value tail = 0.15 → low end.
    series = [0.10 + (i % 21) * 0.01 for i in range(40)]
    _seed_iv_history(db, "AMD", series, date(2026, 4, 1))

    service = IvRiskService(
        minimum_history_days=30,
        iv_warning_threshold=70.0,
        iv_reject_threshold=85.0,
    )
    computation = service.compute_for_symbol(db=db, symbol="AMD")

    assert computation.data_sufficiency_status == "SUFFICIENT"
    assert computation.iv_rank is not None
    assert 0.0 <= computation.iv_rank <= 100.0


def test_iv_reject_when_current_iv_is_at_max() -> None:
    _, db = create_test_session()

    # Varied history so min != max; final value is the new high.
    series = [0.20 + (i % 21) * 0.01 for i in range(39)] + [0.60]
    _seed_iv_history(db, "AMD", series, date(2026, 4, 1))

    service = IvRiskService(
        minimum_history_days=30,
        iv_warning_threshold=70.0,
        iv_reject_threshold=85.0,
    )
    computation = service.compute_for_symbol(db=db, symbol="AMD")

    assert computation.risk_label == RISK_LABEL_IV_REJECT
    assert computation.iv_rank == 100.0


def test_persist_and_rerun_updates_existing_snapshot() -> None:
    _, db = create_test_session()
    _seed_iv_history(
        db, "AMD",
        [0.20 + (i % 5) * 0.01 for i in range(40)],
        date(2026, 4, 1),
    )

    service = IvRiskService(minimum_history_days=30)
    first = service.refresh_iv_risk(db=db, symbols=["AMD"])
    second = service.refresh_iv_risk(db=db, symbols=["AMD"])

    assert first.snapshots_inserted == 1
    assert second.snapshots_inserted == 0
    assert second.snapshots_updated == 1
    assert db.query(IvRiskSnapshot).count() == 1


def test_refresh_records_iv_data_not_available_snapshot_for_stock_only() -> None:
    _, db = create_test_session()
    service = IvRiskService(minimum_history_days=30)

    result = service.refresh_iv_risk(db=db, symbols=["AMD"])

    assert "AMD" in result.no_data_symbols
    row = db.query(IvRiskSnapshot).one()
    assert row.risk_label == RISK_LABEL_IV_DATA_NOT_AVAILABLE
