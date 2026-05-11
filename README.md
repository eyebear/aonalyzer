# Ao Ao Analyzer

Ao Ao Analyzer is a local equity and options research platform for structured market review, option suitability analysis, decision traceability, memory, and learning.

## Project Identity

Display name:

Ao Ao Analyzer

Repository name:

aoaoanalyzer

## Main Features

- Market data collection
- Option chain collection
- News, filings, earnings, and IV risk tracking
- Technical analysis
- Stock setup detection
- Option suitability analysis
- Target versus breakeven analysis
- Earnings and IV risk review
- Data sufficiency checks
- Hard filter checks
- Action suggestion packages
- Opportunity lifecycle tracking
- Next review triggers
- Do-Not-Touch risk controls
- Rejected But Interesting workflow
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

    aoaoanalyzer
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