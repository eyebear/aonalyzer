# Troubleshooting Guide

## Docker / Compose

- **Services won't start:** `docker compose logs <service>`. Ports
  8000/8501/5434/6379 must be free. `.env` is optional (local overrides only);
  create it with `cp .env.example .env` when you need to change defaults.
- **Rebuild after code changes:** `docker compose up -d --build`.

## Database / migrations

- **`alembic upgrade head` fails to connect:** confirm `DATABASE_URL` and that
  Postgres is healthy (`docker compose ps`). Host port is `5434`.
- **`extension "vector" is not available`:** pgvector is optional. Migration
  0001 only enables it when the server ships it (the compose
  `pgvector/pgvector:pg16` image does; vanilla `postgres:16` does not).
  Embeddings are stored as portable JSON either way.
- **Table missing for a feature:** run `alembic upgrade head` — every
  ORM table is created by migrations 0001/0002. The API container applies
  migrations on startup; `ensure_tables` remains only as a test/dev fallback.
- **"Table already defined" on import:** a duplicate ORM table name — check the
  registry; reuse the existing model rather than redefining a table.

## Redis

- **Connection refused:** confirm `REDIS_URL` and that the redis container is up.
  Redis is optional for analysis; the scheduler tolerates its absence.

## API

- **500 on a data-quality/sufficiency route in tests:** ensure the route's
  `ensure_*_tables` binds to the session engine (`db.get_bind()`), not a
  module-level engine.
- **Route 404 for a dynamic path:** static sub-paths must be registered before
  `/{param}` catch-alls (e.g. `/rejections/interesting` before `/{symbol}`).

## Dashboard

- **Page can't reach the API:** the dashboard reads `API_BASE_URL`. In Docker it
  is `http://aonalyzer-api:8000`; locally `http://localhost:8000`.
- **A page errors on import:** dashboard pages are runtime-only; pure logic lives
  in `app/ui_experience`. Run `python -c "import ast,pathlib; [ast.parse(p.read_text()) for p in pathlib.Path('app/dashboard').rglob('*.py')]"`.

## AI providers

- **Chat says "degraded":** no provider is configured (expected). Set a provider
  in Settings or via env vars. Degraded answers are deterministic, not errors.
- **Provider stays NOT_CONFIGURED:** set the matching API key / base URL.

## Option data

- **"Option data not available" everywhere:** that is correct when no option
  data is pasted — it is a prompt, not a rejection. Stock-only analysis still
  works. Paste a contract on the Ticker Analyzer page to enable option analysis.

## Tests

- Python 3.11+ is required. Create a venv, `pip install -r requirements.txt`,
  then `pytest -q`. Tests use in-memory SQLite and need no external services.
