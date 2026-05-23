# Refresh Schedule Guide

Aonalyzer refreshes data both automatically (APScheduler) and manually
(dashboard buttons / API). Every refresh is recorded in `agent_runs`.

## Automatic schedule (Balanced Research Default)

| Job | Frequency |
|-----|-----------|
| Market data | every 30 min (market hours) |
| Option chain placeholder | every 60 min |
| News | every 60 min |
| Watchlist news | every 30 min |
| Filings | every 60 min |
| Earnings calendar | daily |
| IV risk | every 60 min |
| Recommendations | after market close + manual |
| Outcome tracking | after market close |
| Learning report | weekly |

Frequencies come from the active strategy profile and the `*_refresh_minutes`
settings; override them in Settings or via environment variables.

## Manual refresh

- **Home** → *Manual Refresh* buttons (Refresh All / Market Data / News /
  Earnings / IV Risk / Run Recommendations).
- **Ticker Analyzer** → *Refresh This Ticker*, *Refresh This Ticker News*,
  *Re-analyze This Ticker*.
- **API**: `POST /api/agent/refresh/{market-data|news|earnings|iv-risk|all}`,
  `POST /api/agent/run/recommendations`, `POST /api/tickers/{symbol}/refresh/...`.

## Full pipeline

`POST /api/pipeline/run` (or `FullPipeline().run(db)`) runs the complete local
flow end to end: refresh steps → optional option suitability → decisions →
action suggestions → lifecycle/review → worklist → outcome/memory updates →
dashboard validation. It is safe to run repeatedly and never fails because
option data is missing.
