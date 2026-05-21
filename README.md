# Aonalyzer

Aonalyzer is a local equity and options research platform for structured market review, option suitability analysis, decision traceability, memory, and learning.

## Project Status

Aonalyzer is built in sequential, independently testable phases.

- **Completed: Phases 0–26.** Phases 0–18 cover the project and local runtime foundation, centralized configuration and strategy profiles, the database and FastAPI foundations, the agent scheduler and refresh framework, data-quality and data-sufficiency tracking, market data collection, manual option handling, news/filings/macro/event normalization, the earnings calendar and optional IV history, the technical-analysis engine, support/resistance/entry/target/stop math, market regime and sector strength, stock setup detection, the optional option-suitability engine, the pretrained-model layer foundation, the AI provider manager, and AI-assisted event and manual-option-text analysis. Phase 19 added the data sufficiency gate that separates blocking stock-data issues from non-blocking option, news, IV, earnings, and memory warnings. Phase 20 added the hard filter gate that enforces non-negotiable stock rules (risk/reward, price extension, market regime, earnings risk) and optional option rules (DTE, target-vs-breakeven, spread, open interest, IV extreme). Phase 21 added the decision intelligence layer that combines the sufficiency and hard-filter outputs with event-risk and memory-risk into a final action label, priority score, confidence score, and decision trace. Phase 22 added the action suggestion layer that turns each final decision into a structured action package with entry condition, invalidation condition, upgrade/downgrade conditions, watch condition, next-review trigger guidance, and concrete action items. Phase 23 added rejection intelligence with a dedicated rejected-candidates and rejection-reasons store, per-cause explainers, and a "rejected but interesting" bucket. Phase 24 added Do-Not-Touch risk control with active freezes, an audit-trail history, release condition builder, and expiration monitor. Phase 25 added persistent opportunity lifecycle tracking across READY/WATCH/WAIT/WAIT_FOR_MANUAL_OPTION_INPUT/REJECTED/INSUFFICIENT_DATA states, with reactivation detection and user-review tracking. Phase 26 added the next-review trigger engine and review queue that arm per-symbol trigger conditions from the current lifecycle state and surface due reviews when those conditions fire.
- **Next planned: Phase 27.**

The platform is stock-first and non-blocking by design: option data is always optional, and missing or incomplete option data never blocks stock-only analysis. The system never invents missing option values. Missing option data is also never a rejection, never a Do-Not-Touch freeze, and never an automatic review queue entry on its own. AI providers and pretrained models are disabled by default; the system runs fully in a deterministic fallback mode and degrades gracefully when they are unavailable.

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
- Data sufficiency gate (Phase 19)
- Hard filter gate (Phase 20)
- Decision intelligence layer with priority and confidence scoring (Phase 21)
- Action suggestion packages with entry/invalidation/upgrade/downgrade conditions and concrete action items (Phase 22)
- Rejection intelligence with rejected-but-interesting bucket and per-cause explainers (Phase 23)
- Do-Not-Touch temporary freezes with release conditions and expiration sweep (Phase 24)
- Persistent opportunity lifecycle tracking with reactivation and user review (Phase 25)
- Next-review trigger engine and review queue (Phase 26)
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