from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.data_quality.data_quality_models import DataFreshness
from app.database.base import Base
from app.database.models import Event
from app.filings.filing_service import FilingService


class FakeFilingSource:
    source_id = "fake_filing"
    source_name = "Fake Filing"

    def __init__(self, items_by_symbol: dict[str, list[dict]]) -> None:
        self._items_by_symbol = items_by_symbol

    def fetch_ticker_filings(self, symbol: str) -> list[dict]:
        return list(self._items_by_symbol.get(symbol.upper(), []))


def create_test_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return engine, SessionLocal()


def test_filing_service_inserts_8k_filing_with_high_importance() -> None:
    _, db = create_test_session()

    source = FakeFilingSource(
        items_by_symbol={
            "AMD": [
                {
                    "title": "AMD 8-K material event filing",
                    "url": "https://www.sec.gov/Archives/amd-8k",
                    "summary": "Material event disclosure.",
                    "filing_type": "8-K",
                }
            ]
        }
    )

    service = FilingService(sources=[source])
    result = service.refresh_ticker_filings(db=db, symbols=["AMD"])

    assert result.events_inserted == 1
    row = db.query(Event).one()
    assert row.event_type == "FILING"
    assert row.importance_level == "HIGH"
    assert row.source_url == "https://www.sec.gov/Archives/amd-8k"
    assert (row.event_metadata_json or {}).get("filing_type") == "8-K"


def test_filing_service_dedupes_repeat_runs() -> None:
    _, db = create_test_session()

    item = {
        "title": "AMD 10-Q quarterly filing",
        "url": "https://www.sec.gov/Archives/amd-10q",
        "filing_type": "10-Q",
    }
    source = FakeFilingSource(items_by_symbol={"AMD": [item]})
    service = FilingService(sources=[source])

    first = service.refresh_ticker_filings(db=db, symbols=["AMD"])
    second = service.refresh_ticker_filings(db=db, symbols=["AMD"])

    assert first.events_inserted == 1
    assert second.events_inserted == 0
    assert second.duplicate_events == 1
    assert db.query(Event).count() == 1


def test_filing_service_no_symbols_marks_freshness_missing() -> None:
    _, db = create_test_session()

    service = FilingService(sources=[FakeFilingSource(items_by_symbol={})])
    result = service.refresh_ticker_filings(db=db, symbols=[])

    freshness = (
        db.query(DataFreshness)
        .filter(DataFreshness.data_category == "filings")
        .one_or_none()
    )
    assert freshness is not None
    assert freshness.freshness_status == "MISSING"
    assert result.events_inserted == 0


def test_filing_service_empty_source_does_not_raise() -> None:
    _, db = create_test_session()

    service = FilingService(sources=[FakeFilingSource(items_by_symbol={})])
    result = service.refresh_ticker_filings(db=db, symbols=["AMD"])

    assert result.events_inserted == 0
    assert "AMD" in result.successful_symbols or "AMD" in result.failed_symbols
