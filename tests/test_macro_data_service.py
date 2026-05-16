from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.data_quality.data_quality_models import DataFreshness
from app.database.base import Base
from app.database.models import Event
from app.macro.macro_data_service import MacroDataService


class FakeMacroSource:
    source_id = "fake_macro"
    source_name = "Fake Macro"

    def __init__(self, items: list[dict]) -> None:
        self._items = items

    def fetch_macro_events(self) -> list[dict]:
        return list(self._items)


def create_test_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return engine, SessionLocal()


def test_macro_service_inserts_high_importance_fomc_event() -> None:
    _, db = create_test_session()

    source = FakeMacroSource(
        items=[
            {
                "title": "FOMC raises rates by 25bps",
                "url": "https://www.federalreserve.gov/fomc/announcement",
                "summary": "Fed funds rate decision.",
            }
        ]
    )

    service = MacroDataService(sources=[source])
    result = service.refresh_macro_events(db=db)

    assert result.events_inserted == 1

    row = db.query(Event).one()
    assert row.event_type == "MACRO"
    assert row.importance_level == "HIGH"
    assert row.symbol is None
    assert row.source_url == "https://www.federalreserve.gov/fomc/announcement"


def test_macro_service_dedupes_repeat_events() -> None:
    _, db = create_test_session()

    item = {
        "title": "CPI release: prices up 2.3% YoY",
        "url": "https://www.bls.gov/news.release/cpi.htm",
    }
    source = FakeMacroSource(items=[item])
    service = MacroDataService(sources=[source])

    first = service.refresh_macro_events(db=db)
    second = service.refresh_macro_events(db=db)

    assert first.events_inserted == 1
    assert second.events_inserted == 0
    assert second.duplicate_events == 1


def test_macro_service_handles_empty_source() -> None:
    _, db = create_test_session()
    service = MacroDataService(sources=[FakeMacroSource(items=[])])

    result = service.refresh_macro_events(db=db)

    assert result.events_inserted == 0
    freshness = (
        db.query(DataFreshness)
        .filter(DataFreshness.data_category == "macro")
        .one_or_none()
    )
    assert freshness is not None
    assert freshness.freshness_status == "MISSING"
