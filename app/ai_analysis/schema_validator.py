"""Schema validation for AI output (Phase 18, step 18.4).

Rejects malformed AI output: missing required keys, wrong container types, or
values outside an allowed set. Validation is data-only (no exceptions on bad
input) so callers can cleanly fall back when AI output is unusable.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ValidationResult:
    is_valid: bool
    errors: list[str] = field(default_factory=list)


def validate_schema(
    payload: Any,
    *,
    required_fields: Iterable[str],
    list_fields: Iterable[str] = (),
    allowed_values: Mapping[str, Iterable[str]] | None = None,
) -> ValidationResult:
    errors: list[str] = []

    if not isinstance(payload, dict):
        return ValidationResult(False, ["Payload is not a JSON object."])

    for field_name in required_fields:
        if field_name not in payload or payload[field_name] is None:
            errors.append(f"Missing required field: {field_name}")

    for field_name in list_fields:
        if field_name in payload and payload[field_name] is not None:
            if not isinstance(payload[field_name], list):
                errors.append(f"Field '{field_name}' must be a list.")

    if allowed_values:
        for field_name, allowed in allowed_values.items():
            if field_name in payload and payload[field_name] is not None:
                value = str(payload[field_name]).upper()
                allowed_upper = {str(a).upper() for a in allowed}
                if value not in allowed_upper:
                    errors.append(
                        f"Field '{field_name}' value '{payload[field_name]}' "
                        f"not in allowed set {sorted(allowed_upper)}."
                    )

    return ValidationResult(len(errors) == 0, errors)


def coerce_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def coerce_str_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if value is None or value == "":
        return []
    return [str(value)]


__all__ = ["ValidationResult", "coerce_str", "coerce_str_list", "validate_schema"]
