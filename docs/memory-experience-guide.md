# Memory & Experience Guide

Aonalyzer learns from real, tracked outcomes. It never invents conclusions and
never lets memory override deterministic decision gates.

## Layers

### Outcome tracking (Phases 38–40)
- **Signal outcomes** — 5/10/20/30-day forward stock returns, target/stop hits
  for each past recommendation. Option outcome is recorded as *unavailable*
  unless real manual option data existed (then a transparent delta-based
  estimate). Returns are computed only when enough price history exists.
- **Override outcomes** — your actions vs the system suggestion, classified
  later (USER_RIGHT / SYSTEM_RIGHT / NEUTRAL / PENDING) from forward returns.
- **Rejection & Do-Not-Touch outcomes** — whether a rejection/freeze was useful
  or too strict. `would_option_have_worked` stays `UNAVAILABLE` unless real
  option data existed (no fake backfill).

### Case memory
Reusable lessons built from outcomes, including the key case types
`STOCK_RIGHT_OPTION_WRONG` (stock thesis right, option lost) and
`STOCK_RIGHT_OPTION_MISSING` (stock right, no option data to evaluate), plus
`MANUAL_OPTION_ANALYSIS`, `SIGNAL_OUTCOME`, `REJECTION_OUTCOME`, `OVERRIDE`, and
`DO_NOT_TOUCH`. Each case preserves its source reference, decision context,
option-data availability, outcome type, and a plain-language lesson.

### Vector memory
Embeds case memory, overrides, rejected cases, manual option snapshots, and
action suggestions into `memory_embeddings`. Uses sentence-transformers when
available, otherwise a deterministic hash embedding so search works offline.
pgvector is enabled best-effort on PostgreSQL; the portable cosine search works
regardless. Vector memory is supporting context only — it influences
confidence/warnings/explanations, never the deterministic gates or final label.

### Skill memory
Named, versioned skills (e.g. `PULLBACK_LONG_SETUP`, `MANUAL_OPTION_TEXT_READER`,
`OPTION_SUITABILITY_CHECK`, `BREAKEVEN_REALITY_CHECK`, `IV_RISK_FILTER`,
`STOCK_RIGHT_OPTION_WRONG_ANALYZER`, ...) with measured performance: target-hit
rate, stop-first rate, stock-right/option-wrong rate, manual-option-reader
usefulness, and an expected-value proxy. Metrics are recorded and exposed; skill
behavior is never silently changed by them.

### Learning reports
Weekly summaries of successes, failures, stock-right/option-wrong cases, manual
option usage, rejected & Do-Not-Touch outcomes, user overrides, skill
performance, and experience usage. Missing option data is reported as missing,
never converted into option success/failure.

### Improvement engine + champion/challenger
Generates explainable, **approval-gated** suggestions (DTE, IV threshold,
breakeven margin, manual-option prompt, Do-Not-Touch, override-based). The
champion/challenger engine shadow-tests a candidate rule against recorded
outcomes without changing any active decision. Nothing is applied without
explicit user approval.

## How to use it

- `POST /api/outcomes/signals/run` and `/api/outcomes/rejections/run` track
  outcomes (also run by the after-close pipeline).
- `POST /api/memory/cases/build` converts outcomes into cases.
- `POST /api/memory/vector/ingest` then `/api/memory/vector/search` for retrieval.
- `POST /api/memory/skills/compute` registers skills + recomputes metrics.
- `POST /api/learning/reports/generate` and `/api/learning/improvements/generate`.
