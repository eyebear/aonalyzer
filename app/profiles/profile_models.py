from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class StrategyProfileType(StrEnum):
    BALANCED = "BALANCED"
    CONSERVATIVE = "CONSERVATIVE"
    AGGRESSIVE = "AGGRESSIVE"
    CUSTOM = "CUSTOM"


class StrategyProfile(BaseModel):
    profile_name: str
    profile_type: StrategyProfileType
    profile_version: str

    stock_thesis_horizon_min_trading_days: int = Field(ge=1)
    stock_thesis_horizon_max_trading_days: int = Field(ge=1)

    option_dte_min: int = Field(ge=1)
    option_dte_max: int = Field(ge=1)

    premium_min_usd: int = Field(ge=0)
    premium_max_usd: int = Field(ge=0)

    minimum_risk_reward: float = Field(ge=0)

    reject_if_target_below_breakeven: bool
    minimum_target_breakeven_margin_percent: float = Field(ge=0)

    iv_warning_threshold: int = Field(ge=0, le=100)
    iv_reject_threshold: int = Field(ge=0, le=100)

    earnings_risk_window_days: int = Field(ge=0)

    market_data_refresh_minutes: int = Field(ge=1)
    option_chain_refresh_minutes: int = Field(ge=1)
    news_refresh_minutes: int = Field(ge=1)
    watchlist_news_refresh_minutes: int = Field(ge=1)
    filing_refresh_minutes: int = Field(ge=1)
    earnings_calendar_refresh: str
    iv_risk_refresh_minutes: int = Field(ge=1)

    recommendation_job: str
    outcome_tracking_job: str
    learning_report: str

    hard_filters_can_be_bypassed: bool = False

    @model_validator(mode="after")
    def validate_ranges(self) -> "StrategyProfile":
        if self.stock_thesis_horizon_min_trading_days > self.stock_thesis_horizon_max_trading_days:
            raise ValueError(
                "stock_thesis_horizon_min_trading_days cannot exceed "
                "stock_thesis_horizon_max_trading_days"
            )

        if self.option_dte_min > self.option_dte_max:
            raise ValueError("option_dte_min cannot exceed option_dte_max")

        if self.premium_min_usd > self.premium_max_usd:
            raise ValueError("premium_min_usd cannot exceed premium_max_usd")

        if self.iv_warning_threshold > self.iv_reject_threshold:
            raise ValueError("iv_warning_threshold cannot exceed iv_reject_threshold")

        if self.hard_filters_can_be_bypassed:
            raise ValueError("hard filters cannot be bypassed by any strategy profile")

        return self


class ActiveProfileResponse(BaseModel):
    active_profile_name: str
    active_profile_version: str
    profile: StrategyProfile


class ProfileListResponse(BaseModel):
    profiles: list[StrategyProfile]