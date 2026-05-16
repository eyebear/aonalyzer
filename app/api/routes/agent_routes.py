from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.agent.agent_status_reporter import agent_status_reporter
from app.agent.earnings_calendar_refresh_job import run_earnings_calendar_refresh_job
from app.agent.filing_refresh_job import run_filing_refresh_job
from app.agent.iv_risk_refresh_job import run_iv_risk_refresh_job
from app.agent.macro_refresh_job import run_macro_refresh_job
from app.agent.manual_refresh_controller import manual_refresh_controller
from app.agent.market_data_refresh_job import run_market_data_refresh_job
from app.agent.news_refresh_job import run_news_refresh_job
from app.agent.option_chain_refresh_job import run_option_chain_refresh_job
from app.agent.scan_schedule_manager import scan_schedule_manager
from app.agent.scheduler import agent_scheduler
from app.agent.stock_setup_refresh_job import run_stock_setup_refresh_job
from app.agent.technical_refresh_job import run_technical_refresh_job
from app.api.dto import (
    AgentRunListResponse,
    AgentRunResponse,
    AgentStatusResponse,
    ApiMessageResponse,
)
from app.database.connection import get_db_session

router = APIRouter(prefix="/api/agent", tags=["agent"])


class MarketDataRefreshRequest(BaseModel):
    symbols: list[str] | None = None
    include_daily: bool = True
    include_intraday: bool = True
    daily_period: str = "6mo"
    intraday_period: str = "1d"
    intraday_interval: str = "5m"


class OptionChainRefreshRequest(BaseModel):
    symbols: list[str] | None = None
    max_expirations: int = 4


class NewsRefreshRequest(BaseModel):
    symbols: list[str] | None = None


class FilingRefreshRequest(BaseModel):
    symbols: list[str] | None = None


class MacroRefreshRequest(BaseModel):
    pass


class TechnicalRefreshRequest(BaseModel):
    symbols: list[str] | None = None


class EarningsRefreshRequest(BaseModel):
    symbols: list[str] | None = None
    skip_risk_snapshot: bool = False


class IvRiskRefreshRequest(BaseModel):
    symbols: list[str] | None = None
    skip_history_fetch: bool = False


class StockSetupRefreshRequest(BaseModel):
    symbols: list[str] | None = None


def _agent_run_to_response(agent_run) -> AgentRunResponse:
    data = agent_status_reporter.run_to_dict(agent_run)
    return AgentRunResponse(**data)


@router.get("/status", response_model=AgentStatusResponse)
def get_agent_status(session: Session = Depends(get_db_session)) -> AgentStatusResponse:
    summary = agent_status_reporter.get_status_summary(session)
    return AgentStatusResponse(**summary)


@router.get("/runs", response_model=AgentRunListResponse)
def list_agent_runs(
    limit: int = Query(default=25, ge=1, le=100),
    session: Session = Depends(get_db_session),
) -> AgentRunListResponse:
    runs = agent_status_reporter.list_recent_runs(session, limit=limit)

    return AgentRunListResponse(
        runs=[_agent_run_to_response(run) for run in runs],
        count=len(runs),
    )


@router.get("/registered-jobs")
def list_registered_jobs() -> dict:
    jobs = agent_scheduler.list_registered_jobs()

    return {
        "jobs": jobs,
        "count": len(jobs),
    }


@router.post("/pause", response_model=ApiMessageResponse)
def pause_automatic_scans() -> ApiMessageResponse:
    schedule = scan_schedule_manager.pause_automatic_scans()

    return ApiMessageResponse(
        message="Automatic scans paused.",
        data={
            "automatic_scans_enabled": schedule.automatic_scans_enabled,
        },
    )


@router.post("/resume", response_model=ApiMessageResponse)
def resume_automatic_scans() -> ApiMessageResponse:
    schedule = scan_schedule_manager.resume_automatic_scans()

    return ApiMessageResponse(
        message="Automatic scans resumed.",
        data={
            "automatic_scans_enabled": schedule.automatic_scans_enabled,
        },
    )


@router.post("/refresh/test", response_model=AgentRunResponse)
def run_test_refresh(session: Session = Depends(get_db_session)) -> AgentRunResponse:
    run = manual_refresh_controller.run_test_refresh(session)
    return _agent_run_to_response(run)


@router.post("/refresh/all", response_model=AgentRunResponse)
def refresh_all(session: Session = Depends(get_db_session)) -> AgentRunResponse:
    run = manual_refresh_controller.refresh_all(session)
    return _agent_run_to_response(run)


@router.post("/refresh/market-data")
def refresh_market_data(
    request: MarketDataRefreshRequest | None = None,
    session: Session = Depends(get_db_session),
) -> AgentRunResponse | dict[str, Any]:
    if request is None:
        run = manual_refresh_controller.refresh_market_data(session)
        return _agent_run_to_response(run)

    return run_market_data_refresh_job(
        db=session,
        symbols=request.symbols,
        triggered_by="USER",
        trigger_source="API",
        include_daily=request.include_daily,
        include_intraday=request.include_intraday,
        daily_period=request.daily_period,
        intraday_period=request.intraday_period,
        intraday_interval=request.intraday_interval,
    )


@router.post("/refresh/options")
def refresh_options(
    request: OptionChainRefreshRequest | None = None,
    session: Session = Depends(get_db_session),
) -> AgentRunResponse | dict[str, Any]:
    if request is None:
        run = manual_refresh_controller.refresh_options(session)
        return _agent_run_to_response(run)

    return run_option_chain_refresh_job(
        db=session,
        symbols=request.symbols,
        triggered_by="USER",
        trigger_source="API",
        max_expirations=request.max_expirations,
    )


@router.post("/refresh/news")
def refresh_news(
    request: NewsRefreshRequest | None = None,
    session: Session = Depends(get_db_session),
) -> AgentRunResponse | dict[str, Any]:
    if request is None:
        run = manual_refresh_controller.refresh_news(session)
        return _agent_run_to_response(run)

    return run_news_refresh_job(
        db=session,
        symbols=request.symbols,
        triggered_by="USER",
        trigger_source="API",
    )


@router.post("/refresh/filings")
def refresh_filings(
    request: FilingRefreshRequest | None = None,
    session: Session = Depends(get_db_session),
) -> AgentRunResponse | dict[str, Any]:
    if request is None:
        run = manual_refresh_controller.refresh_filings(session)
        return _agent_run_to_response(run)

    return run_filing_refresh_job(
        db=session,
        symbols=request.symbols,
        triggered_by="USER",
        trigger_source="API",
    )


@router.post("/refresh/macro")
def refresh_macro(
    request: MacroRefreshRequest | None = None,
    session: Session = Depends(get_db_session),
) -> AgentRunResponse | dict[str, Any]:
    if request is None:
        run = manual_refresh_controller.refresh_macro(session)
        return _agent_run_to_response(run)

    return run_macro_refresh_job(
        db=session,
        triggered_by="USER",
        trigger_source="API",
    )


@router.post("/refresh/technical")
def refresh_technical(
    request: TechnicalRefreshRequest | None = None,
    session: Session = Depends(get_db_session),
) -> AgentRunResponse | dict[str, Any]:
    if request is None:
        run = manual_refresh_controller.refresh_technical(session)
        return _agent_run_to_response(run)

    return run_technical_refresh_job(
        db=session,
        symbols=request.symbols,
        triggered_by="USER",
        trigger_source="API",
    )


@router.post("/refresh/stock-setup")
def refresh_stock_setup(
    request: StockSetupRefreshRequest | None = None,
    session: Session = Depends(get_db_session),
) -> AgentRunResponse | dict[str, Any]:
    if request is None:
        run = manual_refresh_controller.refresh_stock_setup(session)
        return _agent_run_to_response(run)

    return run_stock_setup_refresh_job(
        db=session,
        symbols=request.symbols,
        triggered_by="USER",
        trigger_source="API",
    )


@router.post("/refresh/earnings")
def refresh_earnings(
    request: EarningsRefreshRequest | None = None,
    session: Session = Depends(get_db_session),
) -> AgentRunResponse | dict[str, Any]:
    if request is None:
        run = manual_refresh_controller.refresh_earnings(session)
        return _agent_run_to_response(run)

    return run_earnings_calendar_refresh_job(
        db=session,
        symbols=request.symbols,
        triggered_by="USER",
        trigger_source="API",
        skip_risk_snapshot=request.skip_risk_snapshot,
    )


@router.post("/refresh/iv-risk")
def refresh_iv_risk(
    request: IvRiskRefreshRequest | None = None,
    session: Session = Depends(get_db_session),
) -> AgentRunResponse | dict[str, Any]:
    if request is None:
        run = manual_refresh_controller.refresh_iv_risk(session)
        return _agent_run_to_response(run)

    return run_iv_risk_refresh_job(
        db=session,
        symbols=request.symbols,
        triggered_by="USER",
        trigger_source="API",
        skip_history_fetch=request.skip_history_fetch,
    )


@router.post("/run/recommendations", response_model=AgentRunResponse)
def run_recommendations(session: Session = Depends(get_db_session)) -> AgentRunResponse:
    run = manual_refresh_controller.run_recommendations(session)
    return _agent_run_to_response(run)