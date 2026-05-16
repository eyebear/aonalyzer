from datetime import date, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.data_quality.data_quality_models import DataFreshness
from app.database.base import Base
from app.iv_history.iv_history_service import IvHistoryService
from app.iv_history.iv_models import IvHistoryDay


class FakeIvHistorySource:
    source_id = "fake_iv"
    source_name = "Fake IV History"

    def __init__(self, items_by_symbol: dict[str, list[dict]]) -> None:
        self._items_by_symbol = items_by_symbol

    def fetch_ticker_iv_history(self, symbol: str) -> list[dict]:
        return list(self._items_by_symbol.get(symbol.upper(), []))


class RaisingSource:
    source_id = "raising"
    source_name = "Raising"

    def fetch_ticker_iv_history(self, symbol: str) -> list[dict]:
        raise RuntimeError("blocked")


def create_test_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return engine, SessionLocal()


def test_empty_source_marks_freshness_missing_and_returns_no_data_symbol() -> None:
    _, db = create_test_session()

    service = IvHistoryService(sources=[FakeIvHistorySource({})])
    result = service.refresh_ticker_iv_history(db=db, symbols=["AMD"])

    assert result.records_created == 0
    assert "AMD" in result.no_data_symbols
    freshness = (
        db.query(DataFreshness)
        .filter(DataFreshness.data_category == "iv_history")
        .one_or_none()
    )
    assert freshness is not None
    assert freshness.freshness_status == "MISSING"


def test_inserts_and_dedupes_iv_history_rows() -> None:
    _, db = create_test_session()

    start = date(2026, 5, 1)
    items = [
        {
            "snapshot_date": start + timedelta(days=i),
            "atm_iv_30d": 0.25 + i * 0.001,
        }
        for i in range(10)
    ]
    source = FakeIvHistorySource(items_by_symbol={"AMD": items})
    service = IvHistoryService(sources=[source])

    first = service.refresh_ticker_iv_history(db=db, symbols=["AMD"])
    second = service.refresh_ticker_iv_history(db=db, symbols=["AMD"])

    assert first.rows_inserted == 10
    assert second.rows_inserted == 0
    assert second.rows_updated == 10
    assert db.query(IvHistoryDay).count() == 10


def test_rejects_invalid_rows() -> None:
    _, db = create_test_session()

    items = [
        {"snapshot_date": None, "atm_iv_30d": 0.25},  # bad date
        {"snapshot_date": "2026-05-01", "atm_iv_30d": None},  # bad iv
        {"snapshot_date": "2026-05-01", "atm_iv_30d": -0.1},  # negative iv
        {"snapshot_date": "2026-05-01", "atm_iv_30d": 0.25},  # valid
    ]
    source = FakeIvHistorySource(items_by_symbol={"AMD": items})
    service = IvHistoryService(sources=[source])

    result = service.refresh_ticker_iv_history(db=db, symbols=["AMD"])

    assert result.rows_inserted == 1
    assert result.rejected_items == 3


def test_raising_source_is_isolated() -> None:
    _, db = create_test_session()
    service = IvHistoryService(sources=[RaisingSource()])

    result = service.refresh_ticker_iv_history(db=db, symbols=["AMD"])

    assert result.rows_inserted == 0
    assert result.failed_reasons.get("AMD:raising") == "blocked"
