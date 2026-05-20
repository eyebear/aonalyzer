from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.data_quality.data_quality_checker import (
    DataFreshnessChecker,
    DataQualityChecker,
)
from app.data_quality.data_quality_models import (
    DataFreshness,
    InsufficientDataEvent,
)
from app.database.base import Base
from app.database.connection import SessionLocal, engine

router = APIRouter(prefix="/api/data-quality", tags=["data-quality"])


DEFAULT_DATA_CATEGORIES = [
    "market_data",
    "option_chain",
    "news",
    "filings",
    "macro",
    "company_ir",
    "earnings_calendar",
    "iv_data",
    "iv_history",
    "memory",
]


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_data_quality_tables() -> None:
    Base.metadata.create_all(bind=engine)


@router.get("/status")
def get_data_quality_status(db: Session = Depends(get_db)) -> dict[str, Any]:
    ensure_data_quality_tables()

    freshness_checker = DataFreshnessChecker()
    now = datetime.now(timezone.utc)

    existing_rows = db.query(DataFreshness).all()
    existing_by_category = {
        row.data_category: row
        for row in existing_rows
    }

    freshness_results = []

    for category in DEFAULT_DATA_CATEGORIES:
        row = existing_by_category.get(category)

        if row is None:
            freshness_results.append(
                freshness_checker.check_freshness(
                    data_category=category,
                    latest_success_at=None,
                    now=now,
                )
            )
            continue

        freshness_results.append(
            freshness_checker.check_freshness(
                data_category=row.data_category,
                latest_success_at=row.latest_success_at,
                now=now,
                max_age_minutes=row.max_age_minutes,
            )
        )

    open_events = (
        db.query(InsufficientDataEvent)
        .filter(InsufficientDataEvent.resolved_at.is_(None))
        .order_by(InsufficientDataEvent.created_at.desc())
        .limit(50)
        .all()
    )

    return {
        "status": "OK",
        "checked_at": now.isoformat(),
        "freshness": freshness_results,
        "open_insufficient_data_events": [
            {
                "id": event.id,
                "label": event.label,
                "symbol": event.symbol,
                "data_category": event.data_category,
                "reason": event.reason,
                "severity": event.severity,
                "context": event.context_json or {},
                "created_at": event.created_at.isoformat()
                if event.created_at
                else None,
            }
            for event in open_events
        ],
    }


@router.get("/insufficient-events")
def get_insufficient_data_events(db: Session = Depends(get_db)) -> dict[str, Any]:
    ensure_data_quality_tables()

    events = (
        db.query(InsufficientDataEvent)
        .order_by(InsufficientDataEvent.created_at.desc())
        .limit(100)
        .all()
    )

    return {
        "status": "OK",
        "events": [
            {
                "id": event.id,
                "label": event.label,
                "symbol": event.symbol,
                "data_category": event.data_category,
                "reason": event.reason,
                "severity": event.severity,
                "context": event.context_json or {},
                "created_at": event.created_at.isoformat()
                if event.created_at
                else None,
                "resolved_at": event.resolved_at.isoformat()
                if event.resolved_at
                else None,
            }
            for event in events
        ],
    }


@router.post("/check/sample")
def run_sample_data_quality_check(db: Session = Depends(get_db)) -> dict[str, Any]:
    ensure_data_quality_tables()

    checker = DataQualityChecker()

    results = [
        checker.check_option_data(option_rows=[], symbol="TEST"),
        checker.check_price_history(price_rows=[], symbol="TEST"),
    ]

    created_events = []

    for result in results:
        if result.label.value == "SUFFICIENT":
            continue

        event = InsufficientDataEvent(
            label=result.label.value,
            symbol=result.symbol,
            data_category=result.data_category,
            reason=result.reason,
            severity=result.severity.value,
            context_json=result.context or {},
        )

        db.add(event)
        created_events.append(event)

    db.commit()

    return {
        "status": "OK",
        "results": [result.to_dict() for result in results],
        "created_events": len(created_events),
    }