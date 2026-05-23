# Troubleshooting Guide

## Docker / Compose

- **Services won't start:** `docker compose logs <service>`. Confirm `.env`
  exists (`cp .env.example .env`) and ports 8000/8501/5434/6379 are free.
- **Rebuild after code changes:** `docker compose up -d --build`.

## Database / migrations

- **`alembic upgrade head` fails to connect:** confirm `DATABASE_URL` and that
  Postgres is healthy (`docker compose ps`). Host port is `5434`.
- **Table missing for a Phase 9+ feature:** most non-core tables are created
  lazily via `ensure_tables` on first use. They appear once the relevant service
  runs once. Core tables come from the Alembic migration.
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
