# Environment Variable Guide

All settings live in `app/core/config.py` (`AppSettings`, pydantic-settings) and
can be overridden via environment variables or `.env`. Copy `.env.example` to
`.env` for local Docker. Run `python scripts/validate_env.py` to fail fast on
missing required config.

## Required

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql+psycopg://aonalyzer:...@localhost:5434/aonalyzer` | PostgreSQL DSN |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis URL |
| `API_BASE_URL` | `http://localhost:8000` | FastAPI base URL (used by the dashboard) |
| `DEFAULT_STRATEGY_PROFILE` | `Balanced Research Default` | Active profile |

## Manual option behavior (safe defaults)

| Variable | Default | Description |
|----------|---------|-------------|
| `MANUAL_OPTION_INPUT_ENABLED` | `true` | Allow pasting manual option text |
| `OPTION_TEXT_AI_READER_ENABLED` | `true` | Allow the AI option reader |
| `STRICT_OPTION_PARSER_MODE` | `false` | Require more fields before a parse is usable |
| `ALLOW_STOCK_ONLY_WHEN_OPTIONS_MISSING` | `true` | **Keep true** — missing option data must not block stock-only research |

## AI providers (optional)

`ACTIVE_AI_PROVIDER`, `FALLBACK_AI_PROVIDER` (default `DISABLED`),
`GEMINI_API_KEY`/`GEMINI_MODEL`, `GROK_API_KEY`/`GROK_MODEL`,
`OPENAI_COMPATIBLE_API_KEY`/`_BASE_URL`/`_MODEL`, `OLLAMA_BASE_URL`/`OLLAMA_MODEL`,
`LOCAL_LLM_BASE_URL`/`LOCAL_LLM_MODEL`, `CUSTOM_PROVIDER_BASE_URL`/`_API_KEY`/`_MODEL`.

## Refresh cadence (optional)

`MARKET_DATA_REFRESH_MINUTES`, `OPTION_CHAIN_REFRESH_MINUTES`,
`NEWS_REFRESH_MINUTES`, `WATCHLIST_NEWS_REFRESH_MINUTES`,
`FILING_REFRESH_MINUTES`, `IV_RISK_REFRESH_MINUTES`.

## Models (optional)

`MODELS_ENABLED` (default `false`), `FINBERT_MODEL_NAME`, `EMBEDDINGS_MODEL_NAME`,
etc. With models disabled the system uses deterministic fallbacks.

Required runtime config is validated by `scripts/validate_env.py` (run in CI).
