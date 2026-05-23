from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.manual_refresh_controller import manual_refresh_controller
from app.api.dto import AgentRunResponse, TickerListResponse, TickerResponse
from app.common.service_utils import ensure_tables
from app.database.connection import get_db_session
from app.database.models import Event, Ticker, Watchlist
from app.earnings.earnings_models import EarningsRiskSnapshot
from app.event_normalizer.freshness import EventFreshnessChecker
from app.iv_history.iv_models import IvRiskSnapshot
from app.options.manual_option_input_service import ManualOptionInputService
from app.quant.stock_setup_models import StockSetup
from app.quant.technical_snapshot_models import TechnicalSnapshot

router = APIRouter(prefix="/api/tickers", tags=["tickers"])


class TickerManualOptionInputRequest(BaseModel):
    raw_text: str = Field(min_length=1)
    source_name: str | None = None


def _agent_run_to_response(agent_run) -> AgentRunResponse:
    if isinstance(agent_run, dict):
        return AgentRunResponse(**agent_run)

    return AgentRunResponse.model_validate(agent_run)


@router.get("", response_model=TickerListResponse)
def list_tickers(session: Session = Depends(get_db_session)) -> TickerListResponse:
    statement = (
        select(Ticker)
        .join(Watchlist, Watchlist.ticker_id == Ticker.id)
        .where(Ticker.is_active.is_(True))
        .where(Watchlist.is_active.is_(True))
        .order_by(Ticker.symbol)
    )

    tickers = list(session.scalars(statement).all())

    return TickerListResponse(
        tickers=[TickerResponse.model_validate(ticker) for ticker in tickers],
        count=len(tickers),
    )


@router.post("/{symbol}/refresh/market-data", response_model=AgentRunResponse)
def refresh_ticker_market_data(
    symbol: str,
    session: Session = Depends(get_db_session),
) -> AgentRunResponse:
    run = manual_refresh_controller.refresh_ticker_market_data(session, symbol)
    return _agent_run_to_response(run)


@router.post("/{symbol}/refresh/options", response_model=AgentRunResponse)
def refresh_ticker_options(
    symbol: str,
    session: Session = Depends(get_db_session),
) -> AgentRunResponse:
    run = manual_refresh_controller.refresh_ticker_options(session, symbol)
    return _agent_run_to_response(run)


@router.post("/{symbol}/refresh/news", response_model=AgentRunResponse)
def refresh_ticker_news(
    symbol: str,
    session: Session = Depends(get_db_session),
) -> AgentRunResponse:
    run = manual_refresh_controller.refresh_ticker_news(session, symbol)
    return _agent_run_to_response(run)


@router.post("/{symbol}/options/manual-input")
def create_ticker_manual_option_input(
    symbol: str,
    request: TickerManualOptionInputRequest,
    session: Session = Depends(get_db_session),
) -> dict:
    service = ManualOptionInputService()

    snapshot = service.create_manual_snapshot(
        db=session,
        raw_text=request.raw_text,
        symbol=symbol,
        source_name=request.source_name,
    )

    return {
        "status": "OK",
        "snapshot": snapshot.to_dict(),
    }


@router.post("/{symbol}/analyze", response_model=AgentRunResponse)
def analyze_ticker(
    symbol: str,
    session: Session = Depends(get_db_session),
) -> AgentRunResponse:
    run = manual_refresh_controller.analyze_ticker(session, symbol)
    return _agent_run_to_response(run)


@router.get("/{symbol}/events")
def list_ticker_events(
    symbol: str,
    event_type: str | None = None,
    importance_level: str | None = None,
    source: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(get_db_session),
) -> dict:
    # Test/dev fallback only — no-op on PostgreSQL (schema owned by Alembic).
    ensure_tables(session)

    query = session.query(Event).filter(Event.symbol == symbol.upper())

    if event_type is not None:
        query = query.filter(Event.event_type == event_type.upper())

    if importance_level is not None:
        query = query.filter(Event.importance_level == importance_level.upper())

    if source is not None:
        query = query.filter(Event.source == source)

    events = (
        query.order_by(Event.detected_time.desc(), Event.id.desc())
        .limit(limit)
        .all()
    )

    freshness_checker = EventFreshnessChecker()

    return {
        "status": "OK",
        "symbol": symbol.upper(),
        "count": len(events),
        "events": [
            {
                "id": event.id,
                "event_type": event.event_type,
                "importance_level": event.importance_level,
                "source": event.source,
                "source_url": event.source_url,
                "source_title": event.source_title,
                "symbol": event.symbol,
                "headline": event.headline,
                "raw_summary": event.raw_summary,
                "event_time": event.event_time.isoformat() if event.event_time else None,
                "detected_time": event.detected_time.isoformat() if event.detected_time else None,
                "content_hash": event.content_hash,
                "event_metadata": event.event_metadata_json or {},
                "is_reviewed": event.is_reviewed,
                "freshness": freshness_checker.check(event_time=event.event_time).to_dict(),
            }
            for event in events
        ],
    }


@router.get("/{symbol}/technical-snapshots")
def list_ticker_technical_snapshots(
    symbol: str,
    limit: int = Query(default=30, ge=1, le=500),
    session: Session = Depends(get_db_session),
) -> dict:
    # Test/dev fallback only — no-op on PostgreSQL (schema owned by Alembic).
    ensure_tables(session)

    snapshots = (
        session.query(TechnicalSnapshot)
        .filter(TechnicalSnapshot.symbol == symbol.upper())
        .order_by(
            TechnicalSnapshot.snapshot_date.desc(),
            TechnicalSnapshot.id.desc(),
        )
        .limit(limit)
        .all()
    )

    return {
        "status": "OK",
        "symbol": symbol.upper(),
        "count": len(snapshots),
        "snapshots": [
            {
                "id": s.id,
                "symbol": s.symbol,
                "snapshot_date": s.snapshot_date.isoformat()
                if s.snapshot_date is not None
                else None,
                "data_sufficiency_status": s.data_sufficiency_status,
                "insufficient_indicators": s.insufficient_indicators_json or [],
                "indicators": {
                    "last_close": s.last_close,
                    "last_volume": s.last_volume,
                    "sma_20": s.sma_20,
                    "sma_50": s.sma_50,
                    "sma_200": s.sma_200,
                    "ema_12": s.ema_12,
                    "ema_26": s.ema_26,
                    "rsi_14": s.rsi_14,
                    "macd": s.macd,
                    "macd_signal": s.macd_signal,
                    "macd_histogram": s.macd_histogram,
                    "atr_14": s.atr_14,
                    "bollinger_upper": s.bollinger_upper,
                    "bollinger_middle": s.bollinger_middle,
                    "bollinger_lower": s.bollinger_lower,
                    "volume_ratio_20": s.volume_ratio_20,
                },
            }
            for s in snapshots
        ],
    }


@router.get("/{symbol}/earnings-risk")
def get_ticker_earnings_risk(
    symbol: str,
    session: Session = Depends(get_db_session),
) -> dict:
    # Test/dev fallback only — no-op on PostgreSQL (schema owned by Alembic).
    ensure_tables(session)

    snapshot = (
        session.query(EarningsRiskSnapshot)
        .filter(EarningsRiskSnapshot.symbol == symbol.upper())
        .order_by(
            EarningsRiskSnapshot.snapshot_date.desc(),
            EarningsRiskSnapshot.id.desc(),
        )
        .first()
    )

    if snapshot is None:
        return {
            "status": "OK",
            "symbol": symbol.upper(),
            "snapshot": None,
            "data_sufficiency_status": "EARNINGS_DATA_NOT_AVAILABLE",
            "reason": "No earnings risk snapshot is on file for this symbol.",
        }

    return {
        "status": "OK",
        "symbol": symbol.upper(),
        "data_sufficiency_status": snapshot.data_sufficiency_status,
        "snapshot": {
            "snapshot_date": snapshot.snapshot_date.isoformat()
            if snapshot.snapshot_date is not None
            else None,
            "next_earnings_datetime_utc": snapshot.next_earnings_datetime_utc.isoformat()
            if snapshot.next_earnings_datetime_utc is not None
            else None,
            "days_to_earnings": snapshot.days_to_earnings,
            "earnings_within_window": snapshot.earnings_within_window,
            "earnings_risk_window_days": snapshot.earnings_risk_window_days,
            "earnings_before_expiration": snapshot.earnings_before_expiration,
            "manual_option_expiration_date": snapshot.manual_option_expiration_date.isoformat()
            if snapshot.manual_option_expiration_date is not None
            else None,
            "risk_label": snapshot.risk_label,
            "risk_reason": snapshot.risk_reason,
        },
    }


@router.get("/{symbol}/iv-risk")
def get_ticker_iv_risk(
    symbol: str,
    session: Session = Depends(get_db_session),
) -> dict:
    # Test/dev fallback only — no-op on PostgreSQL (schema owned by Alembic).
    ensure_tables(session)

    snapshot = (
        session.query(IvRiskSnapshot)
        .filter(IvRiskSnapshot.symbol == symbol.upper())
        .order_by(
            IvRiskSnapshot.snapshot_date.desc(),
            IvRiskSnapshot.id.desc(),
        )
        .first()
    )

    if snapshot is None:
        return {
            "status": "OK",
            "symbol": symbol.upper(),
            "snapshot": None,
            "data_sufficiency_status": "IV_DATA_NOT_AVAILABLE",
            "reason": "No IV risk snapshot is on file for this symbol.",
        }

    return {
        "status": "OK",
        "symbol": symbol.upper(),
        "data_sufficiency_status": snapshot.data_sufficiency_status,
        "snapshot": {
            "snapshot_date": snapshot.snapshot_date.isoformat()
            if snapshot.snapshot_date is not None
            else None,
            "current_iv": snapshot.current_iv,
            "iv_rank": snapshot.iv_rank,
            "iv_percentile": snapshot.iv_percentile,
            "iv_history_days_used": snapshot.iv_history_days_used,
            "iv_warning_threshold": snapshot.iv_warning_threshold,
            "iv_reject_threshold": snapshot.iv_reject_threshold,
            "risk_label": snapshot.risk_label,
            "risk_reason": snapshot.risk_reason,
        },
    }


@router.get("/{symbol}/stock-setup")
def get_ticker_stock_setup(
    symbol: str,
    session: Session = Depends(get_db_session),
) -> dict:
    # Test/dev fallback only — no-op on PostgreSQL (schema owned by Alembic).
    ensure_tables(session)

    setup = (
        session.query(StockSetup)
        .filter(StockSetup.symbol == symbol.upper())
        .order_by(StockSetup.snapshot_date.desc(), StockSetup.id.desc())
        .first()
    )

    if setup is None:
        return {
            "status": "OK",
            "symbol": symbol.upper(),
            "setup": None,
            "data_sufficiency_status": "INSUFFICIENT_PRICE_HISTORY",
            "reason": "No stock setup is on file for this symbol.",
        }

    return {
        "status": "OK",
        "symbol": symbol.upper(),
        "data_sufficiency_status": setup.data_sufficiency_status,
        "setup": {
            "snapshot_date": setup.snapshot_date.isoformat()
            if setup.snapshot_date is not None
            else None,
            "current_close": setup.current_close,
            "nearest_support": setup.nearest_support,
            "nearest_resistance": setup.nearest_resistance,
            "swing_low": setup.swing_low,
            "swing_high": setup.swing_high,
            "direction": setup.direction,
            "entry_zone_low": setup.entry_zone_low,
            "entry_zone_high": setup.entry_zone_high,
            "target_price": setup.target_price,
            "stop_price": setup.stop_price,
            "stop_method": setup.stop_method,
            "risk_per_share": setup.risk_per_share,
            "reward_per_share": setup.reward_per_share,
            "stock_risk_reward": setup.stock_risk_reward,
            "insufficient_reasons": setup.insufficient_reasons_json or [],
        },
    }