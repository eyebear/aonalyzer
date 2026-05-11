from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class HealthResponse(BaseModel):
    status: str
    app_name: str
    technical_name: str
    environment: str


class SystemStatusResponse(BaseModel):
    status: str
    app_name: str
    technical_name: str
    environment: str
    active_ai_provider: str
    default_strategy_profile: str
    postgres_host: str
    postgres_port: int
    redis_host: str
    redis_port: int


class ErrorResponse(BaseModel):
    error: str
    detail: str | None = None


class TickerResponse(BaseModel):
    id: int
    symbol: str
    name: str | None
    market: str
    asset_type: str
    currency: str
    exchange: str | None
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class TickerListResponse(BaseModel):
    tickers: list[TickerResponse]
    count: int


class AgentStatusResponse(BaseModel):
    status: str
    latest_run_id: int | None = None
    latest_job_name: str | None = None
    latest_job_status: str | None = None
    latest_started_at: datetime | None = None
    latest_finished_at: datetime | None = None


class AgentRunResponse(BaseModel):
    id: int
    job_name: str
    job_type: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    duration_seconds: float | None
    triggered_by: str
    trigger_source: str
    symbols_processed: int
    records_created: int
    records_updated: int
    records_failed: int
    error_message: str | None

    model_config = ConfigDict(from_attributes=True)


class AgentRunListResponse(BaseModel):
    runs: list[AgentRunResponse]
    count: int


class ApiMessageResponse(BaseModel):
    message: str
    data: dict[str, Any] | None = None