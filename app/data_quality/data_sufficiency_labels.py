from enum import Enum


class DataSufficiencyLabel(str, Enum):
    SUFFICIENT = "SUFFICIENT"

    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    INSUFFICIENT_OPTION_DATA = "INSUFFICIENT_OPTION_DATA"
    INSUFFICIENT_NEWS_DATA = "INSUFFICIENT_NEWS_DATA"
    INSUFFICIENT_IV_DATA = "INSUFFICIENT_IV_DATA"
    INSUFFICIENT_EARNINGS_DATA = "INSUFFICIENT_EARNINGS_DATA"
    INSUFFICIENT_MEMORY_DATA = "INSUFFICIENT_MEMORY_DATA"
    INSUFFICIENT_PRICE_HISTORY = "INSUFFICIENT_PRICE_HISTORY"
    INSUFFICIENT_FILING_DATA = "INSUFFICIENT_FILING_DATA"
    INSUFFICIENT_MACRO_DATA = "INSUFFICIENT_MACRO_DATA"
    INSUFFICIENT_INDICATOR_DATA = "INSUFFICIENT_INDICATOR_DATA"
    INSUFFICIENT_IV_HISTORY = "INSUFFICIENT_IV_HISTORY"
    IV_DATA_NOT_AVAILABLE = "IV_DATA_NOT_AVAILABLE"
    EARNINGS_DATA_NOT_AVAILABLE = "EARNINGS_DATA_NOT_AVAILABLE"
    # Legacy Phase 12/14 spelling, still emitted by ``stock_setup_service``.
    INSUFFICIENT_SETUP_DATA = "INSUFFICIENT_SETUP_DATA"
    # Phase 19 canonical spelling. ``DataSufficiencyGate`` normalizes the legacy
    # ``INSUFFICIENT_SETUP_DATA`` value to this when emitting gate-level
    # blocking labels, while existing services and stored rows keep the legacy
    # value unchanged.
    INSUFFICIENT_STOCK_SETUP_DATA = "INSUFFICIENT_STOCK_SETUP_DATA"
    # Phase 19 non-blocking marker for stock-only decisions when no option
    # data was supplied. The option-suitability engine already uses this same
    # string in ``app.options.option_suitability``; centralizing it here gives
    # the gate a canonical enum member.
    OPTION_DATA_NOT_AVAILABLE = "OPTION_DATA_NOT_AVAILABLE"


class DataFreshnessStatus(str, Enum):
    FRESH = "FRESH"
    STALE = "STALE"
    MISSING = "MISSING"
    UNKNOWN = "UNKNOWN"


class DataQualitySeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    BLOCKING = "BLOCKING"