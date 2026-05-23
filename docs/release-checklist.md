# Release Readiness Checklist

Pass/fail gates that must be satisfied before tagging a release. Items marked
*environment-dependent* require a Docker/Postgres host and are validated in CI
rather than in a sandboxed dev environment.

## Automated gates (run locally + in CI)

| # | Check | Command | Status |
|---|-------|---------|--------|
| 51.1 | Full pytest suite | `.venv/bin/python -m pytest -q` | ✅ 769 passed |
| 51.6 | Missing-option path never blocks stock-only | `pytest tests/test_phase19_26_cross_layer_invariants.py tests/test_ticker_analyzer_flow.py` | ✅ |
| 51.7 | Pasted-option path works | `pytest tests/test_ticker_analyzer_flow.py` | ✅ |
| 51.8 | Malformed/empty option text degrades safely | `pytest tests/test_manual_option_parser.py tests/test_ticker_analyzer_flow.py` | ✅ |
| 51.9 | AI provider disabled mode | `pytest tests/test_chat_service.py` (degraded-state) | ✅ |
| 51.10 | AI provider mocked / schema | `pytest tests/test_ai_analysis_core.py tests/test_ai_providers.py` | ✅ |
| 51.5 | Full orchestration pipeline | `pytest tests/test_governance_settings_pipeline.py` | ✅ |
| 51.14 | Export/import recovery | `pytest tests/test_governance_settings_pipeline.py::test_export_then_import_roundtrip` | ✅ |
| — | Lint | `ruff check .` | ✅ clean |
| — | FastAPI app imports (154 routes) | `python -c "import app.api.main"` | ✅ |
| — | Dashboard pages parse (24 files) | ast.parse over `app/dashboard` | ✅ |
| 50.x | CI workflow YAML valid | `python -c "import yaml,glob;..."` | ✅ |

## Environment-dependent gates (CI / staging only)

| # | Check | Where | Status |
|---|-------|-------|--------|
| 51.2 | Docker Compose full startup | CI `docker` job / VPS | env-dependent |
| 51.3 | Clean-DB migration (`alembic upgrade head`) | CI `test` job (Postgres service) | env-dependent |
| 51.4 | Existing-DB migration upgrade path | CI `test` job | env-dependent |
| 51.11 | Dashboard core pages load (Streamlit runtime) | CI smoke / manual | env-dependent |
| 51.12 | Refresh buttons trigger correct jobs | manual / API contract tests | API tests ✅ |
| 51.13 | `agent_runs` records scheduled + manual runs | `pytest tests/test_agent_scheduler.py tests/test_agent_refresh_routes.py` | ✅ |
| 51.15 | Failure-mode behavior (bad data, missing keys) | covered by service try/except + tests | ✅ |

## Critical contracts (must all hold)

- [x] Missing option data never blocks stock-only analysis.
- [x] Incomplete option data blocks option suitability only.
- [x] No layer invents missing option values.
- [x] AI chat states missing option data and never overrides hard filters.
- [x] Outcome trackers record option outcome as unavailable (never fabricated).
- [x] Rejection logic never treats missing option data as a rejection.
- [x] Do-Not-Touch never triggers from missing option data alone.
- [x] Vector memory never overrides deterministic gates / final labels.
- [x] Improvement suggestions never silently change production rules.
- [x] `allow_stock_only_when_options_missing` defaults to `True`.
- [x] The full pipeline never fails because option data is missing.

## Release steps

1. Confirm all automated gates above are green (`pytest` + `ruff check .`).
2. Confirm CI is green on the target branch (includes the env-dependent gates).
3. Tag the release: `git tag vX.Y.Z && git push --tags` (triggers `release.yml`).
4. Deploy to staging (`deploy-staging.yml`), smoke test, then VPS (`deploy-vps.yml`).
5. Rollback if needed: re-deploy the previous tag (see `docs/ci-cd-guide.md`).
