#!/usr/bin/env python3
"""Phase 50.21 — environment validation.

Fails fast (non-zero exit) when required runtime configuration is missing or
malformed. Optional settings (AI provider keys, etc.) are reported but never
fail the check — the platform runs fully without external AI.

Run: ``python scripts/validate_env.py``
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make ``app`` importable when run from the repo root.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import get_settings  # noqa: E402

# (attribute, human description) — required to be non-empty.
REQUIRED = [
    ("database_url", "PostgreSQL connection URL"),
    ("redis_url", "Redis connection URL"),
    ("api_base_url", "FastAPI base URL"),
    ("default_strategy_profile", "Default strategy profile name"),
]

# Optional settings — reported only.
OPTIONAL = [
    ("active_ai_provider", "Active AI provider (DISABLED is fine)"),
    ("gemini_api_key", "Gemini API key"),
    ("grok_api_key", "Grok API key"),
    ("openai_compatible_api_key", "OpenAI-compatible API key"),
]


def main() -> int:
    settings = get_settings()
    errors: list[str] = []

    for attr, desc in REQUIRED:
        value = getattr(settings, attr, None)
        if value is None or str(value).strip() == "":
            errors.append(f"MISSING required setting '{attr}' ({desc}).")

    # Safe-default invariant (Phase 47): missing option data must not block
    # stock-only research.
    if getattr(settings, "allow_stock_only_when_options_missing", True) is not True:
        print(
            "WARNING: allow_stock_only_when_options_missing is False — "
            "missing option data will block stock-only research."
        )

    for attr, desc in OPTIONAL:
        value = getattr(settings, attr, None)
        status = "set" if value else "not set"
        print(f"optional: {attr} ({desc}): {status}")

    if errors:
        print("\nEnvironment validation FAILED:")
        for error in errors:
            print(f"  - {error}")
        return 1

    print("\nEnvironment validation OK.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
