from enum import Enum


class EventType(str, Enum):
    NEWS = "NEWS"
    FILING = "FILING"
    MACRO = "MACRO"
    COMPANY_IR = "COMPANY_IR"
    OPTION_ANOMALY = "OPTION_ANOMALY"
    TECHNICAL_TRIGGER = "TECHNICAL_TRIGGER"
    RISK_ALERT = "RISK_ALERT"
    SYSTEM_EVENT = "SYSTEM_EVENT"


class ImportanceLevel(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class EventDataCategory(str, Enum):
    NEWS = "news"
    FILINGS = "filings"
    MACRO = "macro"
    COMPANY_IR = "company_ir"


KNOWN_EVENT_TYPES: frozenset[str] = frozenset(item.value for item in EventType)
KNOWN_IMPORTANCE_LEVELS: frozenset[str] = frozenset(item.value for item in ImportanceLevel)
