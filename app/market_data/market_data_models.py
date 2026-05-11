from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String, Text

from app.database.base import Base
from app.database.models import DailyPrice, IntradayPrice


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class FailedTickerLog(Base):
    __tablename__ = "failed_ticker_logs"

    id = Column(Integer, primary_key=True, index=True)

    symbol = Column(String(50), nullable=False, index=True)
    data_category = Column(String(100), nullable=False, index=True)
    source = Column(String(100), nullable=False, default="yfinance")
    reason = Column(Text, nullable=False)

    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)