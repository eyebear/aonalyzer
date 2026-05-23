# Architecture Diagram

A local, Dockerized, stock-first research platform. See
[architecture-20-layers.md](architecture-20-layers.md) for the full layer model.

```
                          ┌─────────────────────────────┐
                          │   Streamlit Dashboard (UI)   │
                          │  Home · Daily Opportunities  │
                          │  Ticker Analyzer · Manual    │
                          │  Option Review · Earnings/IV │
                          │  News · AI Chat · Memory ·   │
                          │  Skills · Learning · Settings│
                          └──────────────┬──────────────┘
                                         │ HTTP (API_BASE_URL)
                                         ▼
   ┌───────────────────────────── FastAPI backend (app/api) ─────────────────────────────┐
   │ health · tickers · profiles · agent · data-quality · market · options · events       │
   │ decisions · actions · rejections · do-not-touch · lifecycle · review · worklist      │
   │ ticker-brief · chat · user-actions · outcomes · memory · learning · governance       │
   │ settings · export-import · pipeline                                                  │
   └───────┬───────────────────────────┬───────────────────────────────┬─────────────────┘
           │                           │                               │
           ▼                           ▼                               ▼
  ┌─────────────────┐        ┌───────────────────┐          ┌────────────────────┐
  │ Decision engine │        │  Memory & learning │          │  AI provider mgr   │
  │ sufficiency →   │        │  signal/rejection/ │          │  DISABLED default  │
  │ hard filters →  │◄──────►│  override outcomes │          │  Gemini/Grok/      │
  │ decision →      │ memory │  case + vector +   │          │  OpenAI-compat/    │
  │ action →        │  risk  │  skill memory      │          │  Ollama/custom     │
  │ rejection/DNT/  │ (advis)│  learning reports  │          │  (option reader,   │
  │ lifecycle/review│        │  improvement engine│          │   research chat)   │
  └───────┬─────────┘        └─────────┬─────────┘          └─────────┬──────────┘
          │                            │                              │
          ▼                            ▼                              ▼
  ┌──────────────────────────── PostgreSQL (+ pgvector) ─────────────────────────────┐
  │ core tables · decision/action snapshots · rejection · do-not-touch · lifecycle · │
  │ review · worklist · briefs · outcomes · case_memory · memory_embeddings · skills · │
  │ learning_reports · improvement_suggestions · governance versions · audit · settings│
  └──────────────────────────────────────────────────────────────────────────────────┘

  ┌──────────────────────┐   ┌──────────────────────┐   ┌──────────────────────────┐
  │ Agent scheduler       │   │ Redis (cache/queue)   │   │ Optional Ollama (LLM)     │
  │ APScheduler jobs +    │   │                       │   │ docker compose --profile  │
  │ FullPipeline (E2E)    │   │                       │   │ llm                       │
  │ → agent_runs          │   │                       │   │                          │
  └──────────────────────┘   └──────────────────────┘   └──────────────────────────┘

  CI/CD (.github/workflows): ci.yml (lint · tests w/ Postgres+Redis · contracts ·
  docker build · compose smoke · dependency audit) · deploy-staging · deploy-vps ·
  release. Runtime: Dockerfile.api · Dockerfile.agent · Dockerfile.dashboard ·
  docker-compose.yml.
```

## Data-flow contract

Stock data drives the deterministic decision. Option data is optional and joins
only at the option-suitability / option-hard-filter steps. Memory and AI are
advisory: they shape confidence, warnings, and explanations but never change the
deterministic gates, the final label, or production rules (improvements are
approval-gated).
