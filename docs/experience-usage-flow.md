# Experience Usage Flow

## Purpose

Ao Ao Analyzer must not only record historical experience.

It must use recorded experience in future decisions.

The system must learn from recommendations, rejected candidates, user overrides, Do-Not-Touch decisions, outcome tracking, similar cases, and user feedback.

## Core Principle

Experience is not passive history.

Experience must feed future decisions through the Memory Layer, Learning Layer, Decision Intelligence Layer, and Action Suggestion Layer.

## Experience Sources

Ao Ao Analyzer records experience from:

- action suggestions
- decision snapshots
- decision traces
- rejected candidates
- Do-Not-Touch items
- opportunity lifecycle transitions
- review triggers
- user actions
- user overrides
- override outcomes
- signal outcomes
- rejection outcomes
- weekly learning reports
- case memory
- skill performance
- AI chat saved notes
- user feedback

## Experience Processing Flow

1. A candidate is generated.
2. The system creates a decision snapshot.
3. The system creates an action suggestion package.
4. The candidate enters opportunity lifecycle tracking.
5. The user reviews, watches, ignores, rejects, or manually trades.
6. The system records the user action.
7. If the user acts against the system suggestion, the system records a user override.
8. The system tracks 5d, 10d, 20d, and 30d outcomes.
9. The system classifies whether the suggestion, rejection, wait, freeze, or override was useful.
10. The system creates or updates case memory.
11. The system updates skill performance.
12. The system updates learning reports.
13. The system uses memory retrieval in future decisions.
14. The system uses similar cases as memory risk signals.
15. The system adjusts future confidence breakdown and warning language.
16. The system proposes improvement suggestions.
17. The system tests possible rule changes through champion/challenger before any rule promotion.

## Where Experience Enters Future Decisions

### Data Sufficiency Gate

Past data failures should teach the system when a data source is unreliable.

Examples:

- stale option chains
- missing IV fields
- incomplete earnings calendar
- weak news coverage
- insufficient price history

### Hard Filter Gate

Past failures should support stricter hard filters when evidence shows repeated failure.

Examples:

- target below breakeven caused repeated failures
- spread too wide caused poor option expression
- IV percentile above reject threshold caused stock-right-option-wrong cases
- earnings before expiration caused high option failure rate

### Memory Risk Decision Model

Similar historical cases should be retrieved before final action label classification.

Examples:

- similar success case found
- similar failure case found
- similar stock-right-option-wrong case found
- user previously rejected similar setup
- system warning was previously correct
- system warning was previously too strict

### Confidence Score Engine

Experience should change confidence breakdown.

Examples:

- low sample count reduces memory_confidence
- strong similar success raises memory_confidence
- repeated similar failures reduce signal_confidence
- stale data reduces data_confidence
- AI malformed output reduces ai_output_confidence

### Action Label Classifier

Experience can move a candidate from a stronger label to a weaker label.

Examples:

- READY_TO_RESEARCH can become HIGH_QUALITY_WATCH if similar failures exist
- HIGH_QUALITY_WATCH can become WAIT_FOR_OPTION_IMPROVEMENT if option history is weak
- WATCH_ONLY can become REJECTED_BUT_INTERESTING if stock is valid but option is bad
- any normal label can become DO_NOT_TOUCH if risk history is severe

### Action Suggestion Layer

Experience must shape action items.

Examples:

- add warning about historical IV crush
- add reminder that similar calls previously failed
- add stricter upgrade condition
- add next review trigger based on what worked before
- add a manual review reminder for a repeated user override pattern

## Required Experience Labels

User override labels:

- USER_OVERRIDE_SYSTEM_WARNING
- USER_OVERRIDE_SUCCESS
- USER_OVERRIDE_FAILED
- SYSTEM_WARNING_CORRECT
- SYSTEM_WARNING_TOO_STRICT
- MISSED_OPPORTUNITY
- AVOIDED_CORRECTLY

Case memory labels:

- SUCCESS_CASE
- FAILURE_CASE
- STOCK_RIGHT_OPTION_WRONG
- REJECTED_CORRECTLY
- REJECTED_TOO_STRICT
- USER_OVERRIDE_SUCCESS
- USER_OVERRIDE_FAILED
- MISSED_OPPORTUNITY
- AVOIDED_CORRECTLY

Failure labels:

- STOCK_DIRECTION_WRONG
- STOCK_RIGHT_OPTION_WRONG
- IV_TOO_HIGH
- DTE_TOO_SHORT
- BREAKEVEN_TOO_FAR
- SPREAD_TOO_WIDE
- LOW_OPEN_INTEREST
- ENTRY_TOO_LATE
- TARGET_TOO_OPTIMISTIC
- THETA_DECAY
- NEWS_MISREAD
- EARNINGS_RISK
- MARKET_REGIME_CHANGED
- SECTOR_WEAKNESS

## Example Flow

System output:

Final Action Label: WAIT_FOR_IV_COOLDOWN

Reason:

IV percentile is high and earnings is near.

User action:

I_MANUALLY_TRADED

Immediate record:

USER_OVERRIDE_SYSTEM_WARNING

Later outcome:

The option loses value because IV falls after earnings.

Experience result:

USER_OVERRIDE_FAILED

SYSTEM_WARNING_CORRECT

STOCK_RIGHT_OPTION_WRONG

Future impact:

The system increases caution for similar high-IV pre-earnings long call candidates.

The system may downgrade future similar opportunities from HIGH_QUALITY_WATCH to WAIT_FOR_IV_COOLDOWN or DO_NOT_TOUCH.

## Non-Negotiable Rule

Experience cannot directly auto-change official decision rules.

Experience can:

- warn
- reduce confidence
- affect memory risk decision
- affect action items
- create improvement suggestions
- create challenger rules

Only user-approved champion/challenger promotion can change formal rules.