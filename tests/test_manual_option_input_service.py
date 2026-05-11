from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.options.manual_option_input_service import ManualOptionInputService


def create_test_session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return session_factory()


def test_manual_option_input_service_stores_raw_text_and_parsed_fields() -> None:
    db = create_test_session()
    service = ManualOptionInputService()

    raw_text = (
        "AMD June 19 2026 170 call, stock around 165.20, "
        "bid 8.20 ask 8.80, last 8.50, IV around 42.5%, "
        "delta .48, gamma .025, theta -.09, vega .31, "
        "volume 1200, OI 5400."
    )

    snapshot = service.create_manual_snapshot(
        db=db,
        raw_text=raw_text,
        source_name="Manual Test",
    )

    assert snapshot.id >= 1
    assert snapshot.raw_text == raw_text
    assert snapshot.symbol == "AMD"
    assert snapshot.source_name == "Manual Test"
    assert snapshot.option_type == "CALL"
    assert snapshot.strike == 170.0
    assert snapshot.bid == 8.20
    assert snapshot.ask == 8.80
    assert snapshot.mid_price == 8.5
    assert snapshot.contract_cost == 850.0
    assert snapshot.data_quality_status == "OPTION_TEXT_PARSED"

    snapshots = service.list_manual_snapshots(
        db=db,
        symbol="AMD",
    )

    assert len(snapshots) == 1
    assert snapshots[0].id == snapshot.id


def test_manual_option_input_service_reports_missing_fields() -> None:
    db = create_test_session()
    service = ManualOptionInputService()

    snapshot = service.create_manual_snapshot(
        db=db,
        raw_text="AMD option note. I do not have the bid ask yet.",
    )

    assert snapshot.symbol == "AMD"
    assert snapshot.data_quality_status == "INSUFFICIENT_OPTION_DATA"
    assert "bid" in snapshot.missing_fields
    assert "ask" in snapshot.missing_fields
    assert snapshot.mid_price is None
    assert snapshot.contract_cost is None


def test_manual_option_ai_placeholder_updates_snapshot() -> None:
    db = create_test_session()
    service = ManualOptionInputService()

    snapshot = service.create_manual_snapshot(
        db=db,
        raw_text="AMD June 19 2026 170 call bid 8.20 ask 8.80",
    )

    analyzed = service.analyze_manual_snapshot(
        db=db,
        snapshot_id=snapshot.id,
    )

    assert analyzed.ai_status == "PLACEHOLDER_COMPLETE"
    assert analyzed.ai_summary is not None
    assert analyzed.ai_analysis_json is not None
    assert "option_interpretation_label" in analyzed.ai_analysis_json