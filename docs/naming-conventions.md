# Naming Conventions

## Product Names

Display name:

Ao Ao Analyzer

Technical repository name:

aoaoanalyzer

Python package root:

app

## Required Product Language

Use these words:

- research suggestion
- action suggestion
- candidate review
- opportunity review
- manual review required
- final_action_label
- action_items
- entry_condition
- invalidation_condition
- upgrade_condition
- downgrade_condition
- watch_condition
- next_review_trigger
- decision_trace
- confidence_breakdown
- version_stamp
- data_sufficiency_gate
- hard_filter_gate

## Forbidden Product Language

Do not use these words in user-facing product output:

- buy signal
- sell signal
- guaranteed trade
- auto trade
- execute trade
- broker order
- automatic order
- guaranteed profit

## Python Naming

Use snake_case for:

- files
- functions
- variables
- database fields
- JSON keys

Examples:

- action_suggestion
- research_candidate
- decision_snapshot
- confidence_breakdown
- next_review_trigger
- user_override
- do_not_touch_item

Use PascalCase for Python classes.

Examples:

- ActionSuggestion
- ResearchCandidate
- DecisionSnapshot
- ConfidenceBreakdown
- NextReviewTrigger
- UserOverride

## API Naming

Use plural nouns for list resources.

Examples:

- /api/tickers
- /api/recommendations
- /api/action-suggestions
- /api/agent/runs
- /api/user-actions
- /api/overrides

Use action verbs only for process endpoints.

Examples:

- /api/agent/refresh/all
- /api/agent/run/recommendations
- /api/tickers/{symbol}/analyze

## Database Naming

Use plural table names.

Examples:

- tickers
- watchlists
- daily_prices
- action_suggestions
- decision_snapshots
- user_overrides
- override_outcomes
- agent_runs

Use json suffix for structured JSON fields.

Examples:

- checklist_json
- hard_filter_results_json
- decision_trace_json
- action_items_json
- version_stamp_json

## Label Naming

Use uppercase snake case for enum-style labels.

Examples:

- READY_TO_RESEARCH
- WAIT_FOR_OPTION_IMPROVEMENT
- INSUFFICIENT_OPTION_DATA
- DO_NOT_TOUCH
- USER_OVERRIDE_FAILED

## Service Naming

Use service suffix for orchestration modules.

Examples:

- market_data_service.py
- option_chain_service.py
- ticker_brief_service.py
- chat_service.py

Use engine suffix for decision or scoring modules.

Examples:

- priority_score_engine.py
- confidence_score_engine.py
- state_transition_engine.py

Use builder suffix for output assembly modules.

Examples:

- action_package_formatter.py
- decision_trace_builder.py
- version_stamp_builder.py
- next_review_trigger_builder.py