# Aonalyzer

Aonalyzer is a local equity and options research platform for structured market review, option suitability analysis, decision traceability, memory, and learning.

## Overview

Aonalyzer combines a data and analysis backbone with a research workflow layer:

- **Data & analysis** — configuration and strategy profiles, a PostgreSQL/Redis/FastAPI backbone, a scheduler and refresh framework, data-quality and data-sufficiency tracking, market/news/filings/macro/earnings/IV collection, a technical-analysis engine, support/resistance/entry/target/stop math, market regime and sector strength, stock setup detection, an optional option-suitability engine, a pretrained-model layer, an AI provider manager, AI-assisted event and manual-option-text analysis, the data-sufficiency and hard-filter gates, the decision intelligence and action suggestion layers, rejection intelligence, Do-Not-Touch risk control, persistent opportunity lifecycle tracking, and a next-review trigger engine with a review queue.
- **Research workflow** — Today's Research Worklist, the One-Page Ticker Brief, a progressive-disclosure dashboard (Home command center + beginner/advanced view) with Daily Opportunities / Rejected-But-Interesting / Do-Not-Touch / Ticker Analyzer / Manual Option Review / Earnings-IV Risk / News-Events pages, an AI Research Chat with seven answer modes, user-action and override tracking, signal-outcome tracking (5/10/20/30-day returns), rejection and Do-Not-Touch outcome tracking, case memory, vector memory (pgvector-ready, with a portable cosine fallback), skill memory and performance, weekly learning reports, an approval-gated improvement engine with champion/challenger comparison, versioning and governance, a Settings page, memory export/import (package + CLI), an end-to-end orchestration pipeline, CI/CD quality gates, and the documentation set in `docs/`.

The platform is stock-first and non-blocking by design: option data is always optional, and missing or incomplete option data never blocks stock-only analysis. The system never invents missing option values. Missing option data is also never a rejection, never a Do-Not-Touch freeze, and never an automatic review-queue entry on its own; outcome trackers record an absent option outcome as *unavailable* rather than zero or failed. The AI Research Chat uses only system context, states when option data is missing, and never overrides hard filters. Vector memory and improvement suggestions are supporting/advisory only and never change deterministic gates or production rules without explicit approval. The setting `allow_stock_only_when_options_missing` defaults to `true`. AI providers and pretrained models are disabled by default; the system runs fully in a deterministic fallback mode and degrades gracefully when they are unavailable.

## Documentation

See the [`docs/`](docs) directory:

- [Operating manual](docs/operating-manual.md) — daily workflow
- [Decision flow](docs/decision-flow.md) — stock-only vs option-aware paths
- [Action label guide](docs/action-label-guide.md)
- [Manual option input guide](docs/manual-option-input-guide.md)
- [Refresh schedule guide](docs/refresh-schedule-guide.md)
- [AI provider guide](docs/ai-provider-guide.md)
- [Memory & experience guide](docs/memory-experience-guide.md)
- [Memory export/import guide](docs/export-import-guide.md)
- [Environment variable guide](docs/environment-variables.md)
- [CI/CD guide](docs/ci-cd-guide.md)
- [VPS deployment guide](docs/vps-deployment-guide.md)
- [Troubleshooting guide](docs/troubleshooting.md)
- [Release checklist](docs/release-checklist.md)
- [Architecture diagram](docs/architecture-diagram.md)

## Project Identity

Display name:

Aonalyzer

Repository name:

aonalyzer

## Main Features

- Market data collection
- Option chain collection
- News, filings, earnings, and IV risk tracking
- Technical analysis
- Stock setup detection
- Option suitability analysis
- Target versus breakeven analysis
- Earnings and IV risk review
- Data sufficiency gate
- Hard filter gate
- Decision intelligence layer with priority and confidence scoring
- Action suggestion packages with entry/invalidation/upgrade/downgrade conditions and concrete action items
- Rejection intelligence with rejected-but-interesting bucket and per-cause explainers
- Do-Not-Touch temporary freezes with release conditions and expiration sweep
- Persistent opportunity lifecycle tracking with reactivation and user review
- Next-review trigger engine and review queue
- User action and override tracking
- Outcome tracking
- Case memory
- Vector memory
- Weekly learning reports
- AI provider support
- AI Research Chat
- Memory export and import
- Streamlit dashboard

## Technology Stack

- Python
- FastAPI
- Streamlit
- PostgreSQL
- pgvector
- SQLAlchemy
- Alembic
- Redis
- APScheduler
- pandas
- numpy
- yfinance
- requests
- feedparser
- BeautifulSoup
- scikit-learn
- sentence-transformers
- pytest
- ruff
- Docker Compose

## Project Structure

    aonalyzer
    ├── app
    │   ├── api
    │   ├── agent
    │   ├── data
    │   ├── quant
    │   ├── options
    │   ├── decision
    │   ├── action
    │   ├── lifecycle
    │   ├── review
    │   ├── risk_control
    │   ├── rejection
    │   ├── user_actions
    │   ├── worklist
    │   ├── brief
    │   ├── ai
    │   ├── chat
    │   ├── memory
    │   ├── learning
    │   ├── export_import
    │   ├── governance
    │   ├── profiles
    │   ├── ui_experience
    │   ├── database
    │   ├── core
    │   └── dashboard
    ├── tests
    ├── scripts
    ├── data
    ├── reports
    ├── models
    ├── exports
    ├── docs
    ├── docker-compose.yml
    ├── Dockerfile.api
    ├── Dockerfile.agent
    ├── Dockerfile.dashboard
    ├── .env.example
    ├── requirements.txt
    ├── pyproject.toml
    └── README.md

## Local Python Setup

Create a virtual environment:

    python3 -m venv .venv

Activate it:

    source .venv/bin/activate

Install dependencies:

    pip install -r requirements.txt

Run tests:

    pytest

Run the FastAPI backend:

    uvicorn app.api.main:app --reload --host 0.0.0.0 --port 8000

Open the health endpoint:

    http://localhost:8000/health

Run the Streamlit dashboard:

    streamlit run app/dashboard/main.py

Open the dashboard:

    http://localhost:8501

## Docker Setup

Create your local environment file (the API and agent services read it):

    cp .env.example .env

Build and start the local platform:

    docker compose up --build

Open the FastAPI health endpoint:

    http://localhost:8000/health

Open the dashboard:

    http://localhost:8501

PostgreSQL is available on the host at:

    localhost:5434

Redis is available on the host at:

    localhost:6379

## Optional Local LLM Runtime

The Ollama service is optional and uses a Docker Compose profile.

Start the platform with Ollama:

    docker compose --profile llm up --build

Ollama is available on the host at:

    http://localhost:11434

## Default Strategy Profile

The initial profile is:

Balanced Research Default

Default values:

- Stock thesis horizon: 10 to 25 trading days
- Option DTE: 45 to 90
- Preferred premium: 500 to 1000 USD
- Minimum risk/reward: 2.0
- Minimum target-breakeven margin: 3 percent
- IV warning threshold: 70
- IV reject threshold: 85
- Earnings risk window: 7 days
- Market data refresh: every 30 minutes during market hours
- Option chain refresh: every 60 minutes during market hours
- News refresh: every 60 minutes
- Watchlist news refresh: every 30 minutes
- Filings refresh: every 60 minutes
- Earnings calendar refresh: daily
- IV risk refresh: every 60 minutes
- Recommendations: after market close plus manual run
- Outcome tracking: after market close
- Learning report: weekly