# VPS Deployment Guide

Aonalyzer is a self-contained Docker Compose stack. The same compose file runs
locally and on a VPS.

## Prerequisites

- A VPS with Docker + Docker Compose.
- A domain (optional) pointed at the VPS, with a reverse proxy (e.g. Caddy /
  nginx) terminating TLS in front of the API (`:8000`) and dashboard (`:8501`).

## First deploy

```bash
ssh user@vps
git clone <repo> /opt/aonalyzer && cd /opt/aonalyzer
cp .env.example .env        # then edit secrets / DATABASE_URL / provider keys
docker compose up -d --build
docker compose ps
```

Apply migrations (the API entrypoint can run them, or run manually):

```bash
docker compose exec aonalyzer-api alembic upgrade head
```

## Configuration

- Set production secrets in `.env` (never commit it; `.env` is gitignored).
- Keep `ALLOW_STOCK_ONLY_WHEN_OPTIONS_MISSING=true`.
- Configure an AI provider only if desired — the platform runs fully without one.
- Persistent volumes (`aonalyzer_postgres_data`, `aonalyzer_redis_data`,
  `aonalyzer_exports`, ...) survive `docker compose down`.

## Automated deploy

Use the `deploy-vps.yml` workflow (manual dispatch). Configure these repo
secrets: `VPS_HOST`, `VPS_USER`, `VPS_SSH_KEY`, optional `VPS_APP_DIR`. It runs
`git checkout <ref> && docker compose pull && docker compose up -d --build`.

## Backups

- Database: `docker compose exec aonalyzer-postgres pg_dump ...`.
- Learned memory: export a package (`python -m app.export_import.cli export`)
  and copy it off-host. Restore with the import command.

## Rollback

Re-deploy the previous git tag (`deploy-vps.yml` with `ref=<tag>`), and
`alembic downgrade -1` if a schema change must be reverted. See
[ci-cd-guide.md](ci-cd-guide.md).
