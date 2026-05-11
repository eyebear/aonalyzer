from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.data_quality.data_sufficiency_labels import (
    DataFreshnessStatus,
    DataQualitySeverity,
    DataSufficiencyLabel,
)


@dataclass(frozen=True)
class DataQualityResult:
    label: DataSufficiencyLabel
    data_category: str
    reason: str
    severity: DataQualitySeverity
    symbol: str | None = None
    context: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label.value,
            "data_category": self.data_category,
            "reason": self.reason,
            "severity": self.severity.value,
            "symbol": self.symbol,
            "context": self.context or {},
        }


class DataFreshnessChecker:
    DEFAULT_MAX_AGE_MINUTES = {
        "market_data": 30,
        "option_chain": 60,
        "news": 60,
        "filings": 60,
        "earnings_calendar": 1440,
        "iv_data": 60,
        "memory": 10080,
    }

    def check_freshness(
        self,
        data_category: str,
        latest_success_at: datetime | None,
        now: datetime | None = None,
        max_age_minutes: int | None = None,
    ) -> dict[str, Any]:
        current_time = now or datetime.now(timezone.utc)
        allowed_age = max_age_minutes or self.DEFAULT_MAX_AGE_MINUTES.get(
            data_category,
            60,
        )

        if latest_success_at is None:
            return {
                "data_category": data_category,
                "freshness_status": DataFreshnessStatus.MISSING.value,
                "latest_success_at": None,
                "max_age_minutes": allowed_age,
                "age_minutes": None,
                "is_available": False,
                "reason": f"No successful refresh exists for {data_category}.",
            }

        normalized_latest = self._ensure_timezone(latest_success_at)
        age_minutes = int((current_time - normalized_latest).total_seconds() / 60)

        if age_minutes <= allowed_age:
            status = DataFreshnessStatus.FRESH
            is_available = True
            reason = f"{data_category} is fresh."
        else:
            status = DataFreshnessStatus.STALE
            is_available = False
            reason = (
                f"{data_category} is stale. Age is {age_minutes} minutes, "
                f"allowed maximum is {allowed_age} minutes."
            )

        return {
            "data_category": data_category,
            "freshness_status": status.value,
            "latest_success_at": normalized_latest.isoformat(),
            "max_age_minutes": allowed_age,
            "age_minutes": age_minutes,
            "is_available": is_available,
            "reason": reason,
        }

    def _ensure_timezone(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value


class DataQualityChecker:
    REQUIRED_OPTION_FIELDS = [
        "bid",
        "ask",
        "open_interest",
        "implied_volatility",
    ]

    REQUIRED_NEWS_FIELDS = [
        "source",
        "title",
        "event_time",
    ]

    def check_price_history(
        self,
        price_rows: list[dict[str, Any]] | None,
        symbol: str | None = None,
        min_required_rows: int = 50,
    ) -> DataQualityResult:
        rows = price_rows or []

        if len(rows) < min_required_rows:
            return DataQualityResult(
                label=DataSufficiencyLabel.INSUFFICIENT_PRICE_HISTORY,
                data_category="price_history",
                symbol=symbol,
                reason=(
                    f"Price history is insufficient. Required at least "
                    f"{min_required_rows} rows, found {len(rows)}."
                ),
                severity=DataQualitySeverity.BLOCKING,
                context={
                    "required_rows": min_required_rows,
                    "actual_rows": len(rows),
                },
            )

        invalid_rows = []
        required_fields = ["date", "open", "high", "low", "close", "volume"]

        for index, row in enumerate(rows):
            missing_fields = [
                field for field in required_fields if row.get(field) is None
            ]
            if missing_fields:
                invalid_rows.append(
                    {
                        "index": index,
                        "missing_fields": missing_fields,
                    }
                )

        if invalid_rows:
            return DataQualityResult(
                label=DataSufficiencyLabel.INSUFFICIENT_PRICE_HISTORY,
                data_category="price_history",
                symbol=symbol,
                reason="Price history contains rows with missing OHLCV fields.",
                severity=DataQualitySeverity.BLOCKING,
                context={
                    "invalid_rows": invalid_rows[:20],
                    "invalid_row_count": len(invalid_rows),
                },
            )

        return DataQualityResult(
            label=DataSufficiencyLabel.SUFFICIENT,
            data_category="price_history",
            symbol=symbol,
            reason="Price history is sufficient.",
            severity=DataQualitySeverity.INFO,
            context={
                "actual_rows": len(rows),
            },
        )

    def check_option_data(
        self,
        option_rows: list[dict[str, Any]] | None,
        symbol: str | None = None,
    ) -> DataQualityResult:
        rows = option_rows or []

        if not rows:
            return DataQualityResult(
                label=DataSufficiencyLabel.INSUFFICIENT_OPTION_DATA,
                data_category="option_chain",
                symbol=symbol,
                reason="No option chain records are available.",
                severity=DataQualitySeverity.BLOCKING,
                context={
                    "actual_rows": 0,
                },
            )

        invalid_rows = []

        for index, row in enumerate(rows):
            missing_fields = [
                field for field in self.REQUIRED_OPTION_FIELDS if row.get(field) is None
            ]

            bid = row.get("bid")
            ask = row.get("ask")
            open_interest = row.get("open_interest")

            invalid_numeric_reasons = []

            if bid is not None and bid < 0:
                invalid_numeric_reasons.append("bid cannot be negative")

            if ask is not None and ask < 0:
                invalid_numeric_reasons.append("ask cannot be negative")

            if bid is not None and ask is not None and ask < bid:
                invalid_numeric_reasons.append("ask cannot be lower than bid")

            if open_interest is not None and open_interest < 0:
                invalid_numeric_reasons.append("open_interest cannot be negative")

            if missing_fields or invalid_numeric_reasons:
                invalid_rows.append(
                    {
                        "index": index,
                        "missing_fields": missing_fields,
                        "invalid_numeric_reasons": invalid_numeric_reasons,
                    }
                )

        if invalid_rows:
            return DataQualityResult(
                label=DataSufficiencyLabel.INSUFFICIENT_OPTION_DATA,
                data_category="option_chain",
                symbol=symbol,
                reason="Option chain contains missing or invalid bid, ask, OI, or IV fields.",
                severity=DataQualitySeverity.BLOCKING,
                context={
                    "invalid_rows": invalid_rows[:20],
                    "invalid_row_count": len(invalid_rows),
                    "actual_rows": len(rows),
                },
            )

        return DataQualityResult(
            label=DataSufficiencyLabel.SUFFICIENT,
            data_category="option_chain",
            symbol=symbol,
            reason="Option chain data is sufficient.",
            severity=DataQualitySeverity.INFO,
            context={
                "actual_rows": len(rows),
            },
        )

    def check_iv_data(
        self,
        option_rows: list[dict[str, Any]] | None,
        symbol: str | None = None,
    ) -> DataQualityResult:
        rows = option_rows or []

        if not rows:
            return DataQualityResult(
                label=DataSufficiencyLabel.INSUFFICIENT_IV_DATA,
                data_category="iv_data",
                symbol=symbol,
                reason="No option rows are available for IV validation.",
                severity=DataQualitySeverity.BLOCKING,
                context={
                    "actual_rows": 0,
                },
            )

        invalid_rows = []

        for index, row in enumerate(rows):
            implied_volatility = row.get("implied_volatility")

            if implied_volatility is None:
                invalid_rows.append(
                    {
                        "index": index,
                        "reason": "implied_volatility is missing",
                    }
                )
                continue

            if implied_volatility <= 0:
                invalid_rows.append(
                    {
                        "index": index,
                        "reason": "implied_volatility must be greater than zero",
                    }
                )
                continue

            if implied_volatility > 10:
                invalid_rows.append(
                    {
                        "index": index,
                        "reason": "implied_volatility is unrealistically high",
                    }
                )

        if invalid_rows:
            return DataQualityResult(
                label=DataSufficiencyLabel.INSUFFICIENT_IV_DATA,
                data_category="iv_data",
                symbol=symbol,
                reason="IV data is missing or invalid.",
                severity=DataQualitySeverity.BLOCKING,
                context={
                    "invalid_rows": invalid_rows[:20],
                    "invalid_row_count": len(invalid_rows),
                    "actual_rows": len(rows),
                },
            )

        return DataQualityResult(
            label=DataSufficiencyLabel.SUFFICIENT,
            data_category="iv_data",
            symbol=symbol,
            reason="IV data is sufficient.",
            severity=DataQualitySeverity.INFO,
            context={
                "actual_rows": len(rows),
            },
        )

    def check_news_data(
        self,
        news_rows: list[dict[str, Any]] | None,
        symbol: str | None = None,
    ) -> DataQualityResult:
        rows = news_rows or []

        if not rows:
            return DataQualityResult(
                label=DataSufficiencyLabel.INSUFFICIENT_NEWS_DATA,
                data_category="news",
                symbol=symbol,
                reason="No news records are available.",
                severity=DataQualitySeverity.WARNING,
                context={
                    "actual_rows": 0,
                },
            )

        invalid_rows = []

        for index, row in enumerate(rows):
            missing_fields = [
                field for field in self.REQUIRED_NEWS_FIELDS if row.get(field) is None
            ]

            if missing_fields:
                invalid_rows.append(
                    {
                        "index": index,
                        "missing_fields": missing_fields,
                    }
                )

        if invalid_rows:
            return DataQualityResult(
                label=DataSufficiencyLabel.INSUFFICIENT_NEWS_DATA,
                data_category="news",
                symbol=symbol,
                reason="News data contains records with missing source, title, or event time.",
                severity=DataQualitySeverity.WARNING,
                context={
                    "invalid_rows": invalid_rows[:20],
                    "invalid_row_count": len(invalid_rows),
                    "actual_rows": len(rows),
                },
            )

        return DataQualityResult(
            label=DataSufficiencyLabel.SUFFICIENT,
            data_category="news",
            symbol=symbol,
            reason="News data is sufficient.",
            severity=DataQualitySeverity.INFO,
            context={
                "actual_rows": len(rows),
            },
        )

    def check_earnings_data(
        self,
        earnings_rows: list[dict[str, Any]] | None,
        symbol: str | None = None,
    ) -> DataQualityResult:
        rows = earnings_rows or []

        if not rows:
            return DataQualityResult(
                label=DataSufficiencyLabel.INSUFFICIENT_EARNINGS_DATA,
                data_category="earnings",
                symbol=symbol,
                reason="No earnings calendar records are available.",
                severity=DataQualitySeverity.WARNING,
                context={
                    "actual_rows": 0,
                },
            )

        return DataQualityResult(
            label=DataSufficiencyLabel.SUFFICIENT,
            data_category="earnings",
            symbol=symbol,
            reason="Earnings data is sufficient.",
            severity=DataQualitySeverity.INFO,
            context={
                "actual_rows": len(rows),
            },
        )

    def check_memory_data(
        self,
        memory_rows: list[dict[str, Any]] | None,
        symbol: str | None = None,
        min_required_rows: int = 1,
    ) -> DataQualityResult:
        rows = memory_rows or []

        if len(rows) < min_required_rows:
            return DataQualityResult(
                label=DataSufficiencyLabel.INSUFFICIENT_MEMORY_DATA,
                data_category="memory",
                symbol=symbol,
                reason=(
                    f"Memory data is insufficient. Required at least "
                    f"{min_required_rows} similar memory records, found {len(rows)}."
                ),
                severity=DataQualitySeverity.WARNING,
                context={
                    "required_rows": min_required_rows,
                    "actual_rows": len(rows),
                },
            )

        return DataQualityResult(
            label=DataSufficiencyLabel.SUFFICIENT,
            data_category="memory",
            symbol=symbol,
            reason="Memory data is sufficient.",
            severity=DataQualitySeverity.INFO,
            context={
                "actual_rows": len(rows),
            },
        )

    def collect_blocking_labels(
        self,
        results: list[DataQualityResult],
    ) -> list[str]:
        return [
            result.label.value
            for result in results
            if result.label != DataSufficiencyLabel.SUFFICIENT
            and result.severity == DataQualitySeverity.BLOCKING
        ]

    def collect_all_insufficient_labels(
        self,
        results: list[DataQualityResult],
    ) -> list[str]:
        return [
            result.label.value
            for result in results
            if result.label != DataSufficiencyLabel.SUFFICIENT
        ]