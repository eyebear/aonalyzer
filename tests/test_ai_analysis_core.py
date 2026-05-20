from app.ai_analysis.event_schema import (
    EVENT_ALLOWED_VALUES,
    EVENT_LIST_FIELDS,
    EVENT_REQUIRED_FIELDS,
    EventAnalysisResult,
)
from app.ai_analysis.option_text_schema import OptionTextAnalysisResult
from app.ai_analysis.response_parser import extract_json
from app.ai_analysis.schema_validator import validate_schema


def test_extract_plain_json() -> None:
    assert extract_json('{"a": 1, "b": "x"}') == {"a": 1, "b": "x"}


def test_extract_code_fenced_json() -> None:
    text = '```json\n{"a": 1}\n```'
    assert extract_json(text) == {"a": 1}


def test_extract_json_with_surrounding_prose() -> None:
    text = 'Sure, here is the analysis: {"a": 1, "b": [1, 2]} -- hope that helps!'
    assert extract_json(text) == {"a": 1, "b": [1, 2]}


def test_extract_handles_braces_inside_strings() -> None:
    assert extract_json('{"text": "use {curly} braces"}') == {"text": "use {curly} braces"}


def test_extract_returns_none_for_non_json() -> None:
    assert extract_json("there is no json here") is None
    assert extract_json("") is None
    assert extract_json(None) is None


def test_validate_event_schema_ok() -> None:
    payload = {
        "summary": "x",
        "sentiment": "POSITIVE",
        "price_impact": "NOT_PRICED_IN",
        "key_points": ["a"],
        "confidence": "HIGH",
    }
    result = validate_schema(
        payload,
        required_fields=EVENT_REQUIRED_FIELDS,
        list_fields=EVENT_LIST_FIELDS,
        allowed_values=EVENT_ALLOWED_VALUES,
    )
    assert result.is_valid is True


def test_validate_event_schema_missing_field() -> None:
    result = validate_schema(
        {"summary": "x", "sentiment": "POSITIVE", "price_impact": "UNKNOWN"},
        required_fields=EVENT_REQUIRED_FIELDS,
        allowed_values=EVENT_ALLOWED_VALUES,
    )
    assert result.is_valid is False
    assert any("confidence" in e for e in result.errors)


def test_validate_rejects_bad_enum_value() -> None:
    result = validate_schema(
        {"summary": "x", "sentiment": "BULLISH", "price_impact": "UNKNOWN", "confidence": "LOW"},
        required_fields=EVENT_REQUIRED_FIELDS,
        allowed_values=EVENT_ALLOWED_VALUES,
    )
    assert result.is_valid is False


def test_validate_rejects_non_list() -> None:
    result = validate_schema(
        {"summary": "x", "sentiment": "NEUTRAL", "price_impact": "UNKNOWN",
         "confidence": "LOW", "key_points": "not a list"},
        required_fields=EVENT_REQUIRED_FIELDS,
        list_fields=EVENT_LIST_FIELDS,
        allowed_values=EVENT_ALLOWED_VALUES,
    )
    assert result.is_valid is False


def test_event_result_normalizes_invalid_enum() -> None:
    result = EventAnalysisResult.from_payload({"summary": "s", "sentiment": "weird"})
    assert result.sentiment == "NEUTRAL"
    assert result.price_impact == "UNKNOWN"
    assert result.confidence == "LOW"


def test_option_result_defaults_optional_fields() -> None:
    result = OptionTextAnalysisResult.from_payload(
        {"plain_english_summary": "a long call", "missing_fields": ["iv"]}
    )
    payload = result.to_payload()
    assert set(payload.keys()) == {
        "plain_english_summary",
        "liquidity_comment",
        "greeks_comment",
        "time_decay_comment",
        "iv_comment",
        "breakeven_comment",
        "data_quality_warning",
        "missing_fields",
        "suggested_next_check",
        "option_interpretation_label",
    }
    assert payload["missing_fields"] == ["iv"]
    assert payload["liquidity_comment"] == ""
    assert payload["option_interpretation_label"] == "OPTION_TEXT_REVIEWED"
