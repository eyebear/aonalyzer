# Project Boundaries

## Product Boundary

Ao Ao Analyzer is a local, Dockerized, AI-assisted equity and options research operating system.

The platform helps the user collect market data, option chains, news, filings, earnings data, IV data, technical indicators, option suitability data, memory cases, and learning reports.

The platform produces research suggestions and action suggestion packages for manual review.

The user always makes the final decision manually.

## What the Platform Can Do

Ao Ao Analyzer can:

- collect market data
- collect option chain data
- collect news, filings, macro events, earnings events, and IV data
- calculate technical indicators
- detect stock setup types
- evaluate option suitability
- compare target versus breakeven
- check IV and earnings risk
- generate final_action_label
- generate priority_score
- generate confidence_score
- generate confidence_breakdown
- generate decision_trace
- generate next_review_trigger
- generate action_items
- manage opportunity lifecycle states
- create Do-Not-Touch items
- create Today’s Research Worklist
- generate One-Page Ticker Briefs
- support AI answer modes
- track user actions and overrides
- track future outcomes
- build case memory and learning reports
- export and import system memory

## What the Platform Must Not Do

Ao Ao Analyzer must not:

- connect to a broker account
- place trades
- submit market orders
- submit option orders
- auto-execute trades
- auto-manage live positions
- act as a high-frequency trading system
- claim guaranteed profit
- claim guaranteed accuracy
- present output as financial advice
- use language such as buy signal, sell signal, execute trade, guaranteed trade, or broker order

## Correct Product Language

Use these terms:

- research suggestion
- action suggestion
- candidate review
- opportunity review
- manual review required
- final_action_label
- action_items
- entry_condition
- invalidation_condition
- next_review_trigger
- decision_trace
- confidence_breakdown

Avoid these terms:

- buy signal
- sell signal
- guaranteed trade
- auto trade
- execute trade
- broker order

## Decision Responsibility

Ao Ao Analyzer can explain, rank, filter, warn, and suggest research actions.

Ao Ao Analyzer does not make the final trading decision.

The user makes the final decision manually outside the platform.

## AI Boundary

AI providers can summarize, explain, classify events, format action suggestions, and answer research questions using system context.

AI providers cannot override hard filters.

AI providers cannot invent missing data.

AI providers cannot turn an insufficient-data state into a forced action suggestion.

AI providers cannot bypass Do-Not-Touch controls.

AI providers cannot replace the user’s final manual decision.

## Data Boundary

Ao Ao Analyzer should assume external data may be incomplete, stale, delayed, or wrong.

If required data is missing or low quality, the system must output an insufficient-data state instead of forcing a normal action suggestion.

Required insufficient-data labels include:

- INSUFFICIENT_DATA
- INSUFFICIENT_OPTION_DATA
- INSUFFICIENT_NEWS_DATA
- INSUFFICIENT_IV_DATA
- INSUFFICIENT_EARNINGS_DATA
- INSUFFICIENT_MEMORY_DATA
- INSUFFICIENT_PRICE_HISTORY

## System Principle

Hard filters override scores.

Priority score ranks opportunities.

Action label decides what the user should review next.

A good stock setup does not automatically mean the option expression is good.

Every wait action must have a next review trigger.

Every decision must have a decision trace.

Every decision must have version stamps.

Every user override must be recorded and evaluated later.
