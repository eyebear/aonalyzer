from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.manual_refresh_controller import manual_refresh_controller
from app.api.dto import AgentRunResponse, TickerListResponse, TickerResponse
from app.database.connection import get_db_session
from app.database.models import Ticker, Watchlist
from app.options.manual_option_input_service import ManualOptionInputService

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