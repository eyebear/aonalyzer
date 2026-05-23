# Memory Export / Import Guide

Back up and restore the system's learned memory as a self-describing package.
Imports validate the package structure before restoring any records.

## Package contents

A package is a directory containing:

- `manual_option_snapshots.jsonl`, `option_ai_analysis.jsonl`
- `case_memory.jsonl`, `signal_outcomes.jsonl`, `rejection_outcomes.jsonl`,
  `override_outcomes.jsonl`, `do_not_touch_history.jsonl`, `learning_reports.jsonl`
- `action_suggestions.jsonl`, `lifecycle.jsonl`, `versioned_decisions.jsonl`
- `memory_embeddings.parquet`
- `AI_MEMORY_SUMMARY.md`, `AOAO_PLAYBOOK.md`
- `manifest.json` (schema version + record counts)

## Dashboard

Memory Export / Import page → *Export memory package* / *Validate package* /
*Import package*.

## API

- `POST /api/export-import/export` `{ "output_dir": "exports/..." }` (optional)
- `POST /api/export-import/validate` `{ "package_dir": "..." }`
- `POST /api/export-import/import` `{ "package_dir": "..." }`

## CLI

```
python -m app.export_import.cli export [output_dir]
python -m app.export_import.cli validate <package_dir>
python -m app.export_import.cli import  <package_dir>
```

## Behavior

- Export writes only inside the given output directory (defaults under
  `exports/`, which is gitignored).
- Import is additive and idempotent on natural keys (it never deletes existing
  data) and refuses to restore a package that fails validation.
- ISO date/datetime strings are coerced back to typed columns on import.
