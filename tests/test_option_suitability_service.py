from datetime import date, datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import AppSettings
from app.database.base import Base
from app.options.manual_option_models import ManualOptionSnapshotRecord
from app.options.option_candidate_models import OptionCandidate
from app.options.option_suitability_service import OptionSuitabilityService


def create_test_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return engine, SessionLocal()


def _record(record_id=1, **overrides) -> ManualOptionSnapshotRecord:
    base = dict(
        id=record_id,
        raw_text="AMD call",
        symbol="AMD",
        source_name="manual",
        underlying_price=100.0,
        expiration_date=date.today() + timedelta(days=60),
        option_type="CALL",
        strike=100.0,
        bid=4.9,
        ask=5.1,
        last_price=5.0,
        volume=500,
        open_interest=2000,
        implied_volatility=0.50,
        delta=0.5,
        gamma=None,
        theta=None,
        vega=None,
        rho=None,
        dte=60,
        mid_price=5.0,
        spread_percent=4.0,
        contract_cost=500.0,
        breakeven=105.0,
        breakeven_distance=5.0,
        breakeven_distance_percent=5.0,
        parser_confidence="HIGH",
        missing_fields=[],
        parsed_fields={},
        data_quality_status="USABLE_OPTION_DATA",
        ai_status="NOT_ANALYZED",
        ai_summary=None,
        ai_analysis_json=None,
        created_at=datetime(2026, 5, 15, tzinfo=timezone.utc),
    )
    base.update(overrides)
    return ManualOptionSnapshotRecord(**base)


class _FakeManualService:
    def __init__(self, record: ManualOptionSnapshotRecord | None) -> None:
        self.record = record

    def get_manual_snapshot_by_id(self, db, snapshot_id):
        if self.record is not None and snapshot_id == self.record.id:
            return self.record
        return None


def test_evaluate_snapshot_suitable_persists_candidate() -> None:
    _, db = create_test_session()
    service = OptionSuitabilityService(
        settings=AppSettings(), manual_option_service=_FakeManualService(_record())
    )

    candidate = service.evaluate_snapshot(db, 1)

    assert candidate.suitability_label == "OPTION_SUITABLE"
    assert candidate.is_suitable is True
    assert candidate.breakeven == 105.0
    assert db.query(OptionCandidate).count() == 1


def test_evaluate_snapshot_too_expensive() -> None:
    _, db = create_test_session()
    record = _record(bid=11.9, ask=12.1, last_price=12.0, mid_price=12.0)
    service = OptionSuitabilityService(
        settings=AppSettings(), manual_option_service=_FakeManualService(record)
    )

    candidate = service.evaluate_snapshot(db, 1)
    assert candidate.suitability_label == "STOCK_OK_BUT_OPTION_BAD"
    assert "OPTION_TOO_EXPENSIVE" in (candidate.rejection_labels_json or [])


def test_evaluate_snapshot_is_idempotent() -> None:
    _, db = create_test_session()
    service = OptionSuitabilityService(
        settings=AppSettings(), manual_option_service=_FakeManualService(_record())
    )
    service.evaluate_snapshot(db, 1)
    service.evaluate_snapshot(db, 1)
    assert db.query(OptionCandidate).count() == 1


def test_no_option_fallback_is_non_blocking() -> None:
    _, db = create_test_session()
    service = OptionSuitabilityService(
        settings=AppSettings(), manual_option_service=_FakeManualService(None)
    )

    evaluation = service.evaluate_no_option(db, "AMD")
    assert evaluation.result.suitability_label == "OPTION_DATA_NOT_AVAILABLE"
    assert evaluation.result.is_suitable is False
    # Nothing persisted for the no-data path.
    assert db.query(OptionCandidate).count() == 0


def test_missing_snapshot_raises_value_error() -> None:
    _, db = create_test_session()
    service = OptionSuitabilityService(
        settings=AppSettings(), manual_option_service=_FakeManualService(None)
    )
    try:
        service.evaluate_snapshot(db, 999)
        raise AssertionError("expected ValueError")
    except ValueError:
        pass
