# CI/CD Guide

GitHub Actions workflows live in `.github/workflows/`.

## Workflows

### `ci.yml` — runs on push + pull request to `main`
- **lint** — `ruff check .` (blocking) + `ruff format --check` (advisory, since
  legacy files predate ruff-format).
- **test** — installs deps, validates env (`scripts/validate_env.py`), runs
  `alembic upgrade head`, and `pytest` against PostgreSQL + Redis service
  containers. Uploads `pytest-report.xml` on failure.
- **contracts** — runs the critical-contract suites (decision engine, manual
  option parser, stock-only fallback + cross-layer invariants, AI safety, API
  contracts, export/import).
- **docker** — builds the API and dashboard images, validates `docker compose
  config`, and parses every dashboard page.
- **dependency-audit** — `pip-audit` (non-blocking).

### `deploy-staging.yml` — manual dispatch
Placeholder; runs only when `STAGING_HOST` is configured.

### `deploy-vps.yml` — manual dispatch
SSH `docker compose pull && up -d --build`. Runs only when `VPS_HOST` /
`VPS_USER` / `VPS_SSH_KEY` secrets are configured.

### `release.yml` — runs on `v*` tags
Installs, runs `pytest`, then creates a GitHub release with generated notes.

## Required secrets

| Secret | Used by |
|--------|---------|
| `STAGING_HOST` | staging deploy |
| `VPS_HOST`, `VPS_USER`, `VPS_SSH_KEY`, `VPS_APP_DIR` | VPS deploy |

## Rollback (50.23)

Deployments are immutable per git tag. To roll back:

1. Re-dispatch `deploy-vps.yml` with the previous good tag as `ref`.
2. On the host: `git checkout <previous-tag> && docker compose up -d --build`.
3. If a migration must be reverted, run `alembic downgrade -1` before redeploy.

## Local equivalent

Run the same gates locally before tagging:

```
ruff check .
python scripts/validate_env.py
pytest -q
docker compose config
```
