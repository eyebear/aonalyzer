"""Safe parsing of a provider's text response into JSON (Phase 18, step 18.3).

Providers often wrap JSON in code fences or surround it with prose. This module
extracts the first JSON object as tolerantly as possible, returning ``None`` when
nothing parseable is found -- it never raises.
"""

from __future__ import annotations

import json
import re
from typing import Any

_FENCE_OPEN = re.compile(r"^```[a-zA-Z0-9_-]*\s*\n")
_FENCE_CLOSE = re.compile(r"\n```\s*$")


def _strip_code_fence(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = _FENCE_OPEN.sub("", stripped)
        stripped = _FENCE_CLOSE.sub("", stripped)
    return stripped.strip()


def _first_balanced_object(text: str) -> str | None:
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        char = text[i]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def extract_json(text: str | None) -> dict[str, Any] | None:
    """Return the first JSON object embedded in ``text``, or None."""
    if not text:
        return None

    cleaned = _strip_code_fence(text)

    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    candidate = _first_balanced_object(cleaned)
    if candidate is None:
        return None
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


__all__ = ["extract_json"]
