from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.event_normalizer.event_labels import EventType, ImportanceLevel


HIGH_NEWS_KEYWORDS: tuple[str, ...] = (
    "earnings",
    "merger",
    "acquisition",
    "buyout",
    "guidance",
    "downgrade",
    "upgrade",
    "lawsuit",
    "bankruptcy",
    "fda",
    "approval",
    "investigation",
    "ceo resigns",
    "ceo steps down",
    "halts trading",
    "going private",
    "delist",
    "delisting",
    "recall",
    "data breach",
    "hack",
)

MEDIUM_NEWS_KEYWORDS: tuple[str, ...] = (
    "analyst",
    "price target",
    "partnership",
    "product launch",
    "dividend",
    "buyback",
    "share repurchase",
    "expansion",
    "contract",
)

HIGH_MACRO_KEYWORDS: tuple[str, ...] = (
    "fomc",
    "fed",
    "federal reserve",
    "rate decision",
    "rate hike",
    "rate cut",
    "cpi",
    "ppi",
    "non-farm",
    "nonfarm",
    "payroll",
    "gdp",
    "unemployment",
    "boc",
    "ecb",
    "bank of japan",
    "boj",
)

HIGH_FILING_TYPES: tuple[str, ...] = (
    "8-K",
    "10-K",
    "10-Q",
    "S-1",
    "13D",
    "13G",
)

TRUSTED_SOURCES: tuple[str, ...] = (
    "sec.gov",
    "sec_edgar",
    "fred",
    "federal reserve",
    "bank of canada",
    "reuters",
    "bloomberg",
    "wall street journal",
    "wsj",
    "financial times",
)

RECENT_BOOST_HOURS = 4
STALE_DEMOTE_DAYS = 7


@dataclass(frozen=True)
class ImportanceVerdict:
    level: ImportanceLevel
    reason: str

    def to_dict(self) -> dict[str, str]:
        return {
            "level": self.level.value,
            "reason": self.reason,
        }


class ImportanceClassifier:
    """Deterministic, explainable rules — no AI calls."""

    def __init__(
        self,
        recent_boost_hours: int = RECENT_BOOST_HOURS,
        stale_demote_days: int = STALE_DEMOTE_DAYS,
    ) -> None:
        self.recent_boost_hours = recent_boost_hours
        self.stale_demote_days = stale_demote_days

    def classify(
        self,
        event_type: str,
        headline: str | None,
        source: str | None,
        event_time: datetime | None,
        filing_type: str | None = None,
        now: datetime | None = None,
    ) -> ImportanceVerdict:
        current_time = now or datetime.now(timezone.utc)

        base_level, base_reason = self._classify_base(
            event_type=event_type,
            headline=headline,
            filing_type=filing_type,
        )

        adjusted_level, adjustment_reason = self._apply_source_quality(
            level=base_level,
            source=source,
        )

        recency_level, recency_reason = self._apply_recency(
            level=adjusted_level,
            event_time=event_time,
            now=current_time,
        )

        reason_parts = [base_reason]

        if adjustment_reason:
            reason_parts.append(adjustment_reason)

        if recency_reason:
            reason_parts.append(recency_reason)

        return ImportanceVerdict(
            level=recency_level,
            reason="; ".join(reason_parts),
        )

    def _classify_base(
        self,
        event_type: str,
        headline: str | None,
        filing_type: str | None,
    ) -> tuple[ImportanceLevel, str]:
        normalized_type = (event_type or "").upper()
        normalized_headline = (headline or "").lower()

        if normalized_type == EventType.FILING.value:
            normalized_filing_type = (filing_type or "").upper()

            if normalized_filing_type in HIGH_FILING_TYPES:
                return (
                    ImportanceLevel.HIGH,
                    f"filing_type={normalized_filing_type} is high-importance",
                )

            return (
                ImportanceLevel.MEDIUM,
                "filing event default importance is MEDIUM",
            )

        if normalized_type == EventType.MACRO.value:
            for keyword in HIGH_MACRO_KEYWORDS:
                if keyword in normalized_headline:
                    return (
                        ImportanceLevel.HIGH,
                        f"macro keyword matched: '{keyword}'",
                    )

            return (
                ImportanceLevel.MEDIUM,
                "macro event default importance is MEDIUM",
            )

        if normalized_type == EventType.NEWS.value:
            for keyword in HIGH_NEWS_KEYWORDS:
                if keyword in normalized_headline:
                    return (
                        ImportanceLevel.HIGH,
                        f"news keyword matched: '{keyword}'",
                    )

            for keyword in MEDIUM_NEWS_KEYWORDS:
                if keyword in normalized_headline:
                    return (
                        ImportanceLevel.MEDIUM,
                        f"news keyword matched: '{keyword}'",
                    )

            return (
                ImportanceLevel.LOW,
                "news event default importance is LOW",
            )

        if normalized_type == EventType.COMPANY_IR.value:
            return (
                ImportanceLevel.MEDIUM,
                "company IR event default importance is MEDIUM",
            )

        if normalized_type == EventType.RISK_ALERT.value:
            return (
                ImportanceLevel.HIGH,
                "risk alert defaults to HIGH",
            )

        return (
            ImportanceLevel.LOW,
            f"event_type={normalized_type or 'UNKNOWN'} defaults to LOW",
        )

    def _apply_source_quality(
        self,
        level: ImportanceLevel,
        source: str | None,
    ) -> tuple[ImportanceLevel, str]:
        normalized_source = (source or "").lower()

        if not normalized_source:
            return level, ""

        for trusted in TRUSTED_SOURCES:
            if trusted in normalized_source:
                if level == ImportanceLevel.LOW:
                    return (
                        ImportanceLevel.MEDIUM,
                        f"trusted source '{trusted}' lifted LOW to MEDIUM",
                    )

                return level, f"trusted source '{trusted}'"

        return level, ""

    def _apply_recency(
        self,
        level: ImportanceLevel,
        event_time: datetime | None,
        now: datetime,
    ) -> tuple[ImportanceLevel, str]:
        if event_time is None:
            return level, ""

        normalized_event_time = (
            event_time
            if event_time.tzinfo is not None
            else event_time.replace(tzinfo=timezone.utc)
        )

        age = now - normalized_event_time

        if age >= timedelta(days=self.stale_demote_days):
            if level == ImportanceLevel.HIGH:
                return (
                    ImportanceLevel.MEDIUM,
                    f"event older than {self.stale_demote_days}d demoted HIGH to MEDIUM",
                )

            if level == ImportanceLevel.MEDIUM:
                return (
                    ImportanceLevel.LOW,
                    f"event older than {self.stale_demote_days}d demoted MEDIUM to LOW",
                )

            return level, ""

        if age <= timedelta(hours=self.recent_boost_hours):
            if level == ImportanceLevel.LOW:
                return (
                    ImportanceLevel.MEDIUM,
                    f"event within last {self.recent_boost_hours}h boosted LOW to MEDIUM",
                )

            if level == ImportanceLevel.MEDIUM:
                return (
                    ImportanceLevel.HIGH,
                    f"event within last {self.recent_boost_hours}h boosted MEDIUM to HIGH",
                )

            return level, ""

        return level, ""
