# Ao Ao Analyzer 20-Layer Architecture

## Overview

Ao Ao Analyzer uses a 20-layer architecture.

The system is designed as a local, Dockerized research operating system for equity and options research.

It is not an auto-trading platform.

It is not broker-connected.

It produces structured research suggestions and action suggestion packages for manual review.

## Layer List

1. Data Intelligence Layer
2. Pretrained Model Layer
3. Quant Analysis Layer
4. Options Intelligence Layer
5. Earnings / IV Event Risk Layer
6. Decision Intelligence Layer
7. Action Suggestion Layer
8. Opportunity Lifecycle Layer
9. Review Trigger Layer
10. Do-Not-Touch Risk Control Layer
11. Rejection Intelligence Layer
12. User Override Tracking Layer
13. Memory Layer
14. Learning Layer
15. AI Advisor / Provider Layer
16. AI Research Chat Layer
17. Agent Scheduler / Refresh Layer
18. Memory Export / Import Layer
19. UI Experience / Progressive Disclosure Layer
20. Versioning / Governance Layer

## 1. Data Intelligence Layer

Responsibilities:

- collect market data
- collect option chain data
- collect news
- collect filings
- collect macro data
- collect company IR events
- collect earnings calendar data
- collect IV history
- check data freshness
- check data quality
- normalize events

Main components:

- Market Data Collector
- Option Chain Collector
- News Collector
- Filing Collector
- Macro Collector
- Company IR Collector
- Earnings Calendar Collector
- IV History Collector
- Data Freshness Checker
- Data Quality Checker
- Event Normalizer

## 2. Pretrained Model Layer

Responsibilities:

- provide optional model-based analysis
- support sentiment analysis
- support embeddings
- support auxiliary K-line analysis
- support future outcome models
- track model versions

Main components:

- FinBERT Sentiment Model
- FinGPT / Financial LLM Adapter
- Kronos K-Line Model Adapter
- Sentence-Transformers Embedding Model
- XGBoost / LightGBM Outcome Models
- Model Version Registry
- Local Model Adapter

## 3. Quant Analysis Layer

Responsibilities:

- calculate technical indicators
- detect support and resistance
- estimate market regime
- estimate sector strength
- calculate stock risk/reward
- estimate time to target
- detect setup type

Main components:

- Technical Analysis Engine
- Support / Resistance Engine
- Market Regime Engine
- Sector Strength Engine
- Risk / Reward Engine
- Time-to-Target Estimator
- Setup Detection Engine

## 4. Options Intelligence Layer

Responsibilities:

- filter option chains
- apply DTE filter
- apply premium budget filter
- analyze spread and liquidity
- analyze open interest and volume
- analyze IV risk
- estimate Greeks
- calculate breakeven
- compare target versus breakeven
- check option data quality
- score option suitability

Main components:

- Option Chain Filter
- DTE Filter
- Premium Budget Filter
- Spread / Liquidity Analyzer
- Open Interest / Volume Analyzer
- IV Risk Analyzer
- Greeks Estimator
- Breakeven Reality Checker
- Target vs Breakeven Analyzer
- Option Data Quality Checker
- Option Suitability Scorer

## 5. Earnings / IV Event Risk Layer

Responsibilities:

- track earnings dates
- calculate days to earnings
- detect earnings before expiration
- calculate IV rank
- calculate IV percentile
- detect pre-earnings IV expansion
- estimate post-earnings IV crush risk
- apply earnings risk filters
- check IV data quality
- assign earnings and IV risk labels

Main components:

- Earnings Calendar Service
- Days-to-Earnings Calculator
- Earnings-Before-Expiration Checker
- IV Rank Calculator
- IV Percentile Calculator
- Pre-Earnings IV Expansion Detector
- Post-Earnings IV Crush Risk Estimator
- Earnings Risk Filter
- IV Data Quality Checker
- Earnings / IV Risk Labeler

## 6. Decision Intelligence Layer

Responsibilities:

- run data sufficiency checks
- run hard filter checks
- evaluate stock thesis
- evaluate option expression
- evaluate event and IV risk
- evaluate memory risk
- build opportunity checklist
- calculate priority score
- calculate confidence score
- build confidence breakdown
- classify final action label
- build decision trace
- build final decision snapshot

Main components:

- Data Sufficiency Gate
- Hard Filter Gate
- Stock Thesis Decision Model
- Option Expression Decision Model
- Event / Earnings / IV Risk Decision Model
- Memory Risk Decision Model
- Opportunity Quality Checklist
- Priority Score Engine
- Confidence Score Engine
- Confidence Score Breakdown Builder
- Action Label Classifier
- Decision Trace Builder
- Final Decision Builder

## 7. Action Suggestion Layer

Responsibilities:

- generate suggested action summary
- generate entry condition
- generate option contract criteria
- generate invalidation condition
- generate upgrade condition
- generate downgrade condition
- generate watch condition
- generate next review trigger
- generate action items
- format action package
- handle insufficient-data action output

Main components:

- Suggested Action Summary Builder
- Entry Condition Builder
- Option Contract Criteria Builder
- Invalidation Condition Builder
- Upgrade Condition Builder
- Downgrade Condition Builder
- Watch Condition Builder
- Next Review Trigger Builder
- Action Items Generator
- Insufficient Data Action Builder
- Action Package Formatter

## 8. Opportunity Lifecycle Layer

Responsibilities:

- manage opportunity state
- track lifecycle transitions
- explain state changes
- write lifecycle history
- reactivate old opportunities
- track user review state
- bridge lifecycle to memory

Main components:

- Opportunity State Manager
- Opportunity State Transition Engine
- Opportunity State Reason Builder
- Opportunity Lifecycle History Writer
- Opportunity Reactivation Engine
- User Review State Tracker
- Lifecycle-to-Memory Bridge

## 9. Review Trigger Layer

Responsibilities:

- build next review triggers
- evaluate price triggers
- evaluate option improvement triggers
- evaluate IV cooldown triggers
- evaluate earnings aftermath triggers
- evaluate news triggers
- evaluate data refresh triggers
- build manual review reminders
- generate review queue

Main components:

- Next Review Trigger Engine
- Price Trigger Evaluator
- Option Trigger Evaluator
- IV Cooldown Trigger Evaluator
- Earnings Aftermath Trigger Evaluator
- News Trigger Evaluator
- Data Refresh Trigger Evaluator
- Manual Review Reminder Builder
- Review Queue Generator

## 10. Do-Not-Touch Risk Control Layer

Responsibilities:

- classify temporary freeze situations
- manage temporary freezes
- build release conditions
- monitor freeze expiration
- explain do-not-touch reasons
- write do-not-touch history

Main components:

- Do-Not-Touch Classifier
- Temporary Freeze Manager
- Release Condition Builder
- Freeze Expiration Monitor
- Do-Not-Touch Reason Explainer
- Do-Not-Touch History Writer

## 11. Rejection Intelligence Layer

Responsibilities:

- classify rejection reasons
- detect stock-good-option-bad situations
- generate rejected-but-interesting records
- explain option rejection
- explain breakeven failure
- explain IV and earnings rejection
- explain liquidity rejection
- write rejected candidates to memory
- feed rejection outcomes into learning

Main components:

- Rejection Reason Classifier
- Stock-OK-Option-Bad Detector
- Rejected But Interesting Generator
- Option Rejection Explanation Builder
- Breakeven Failure Explainer
- IV / Earnings Rejection Explainer
- Liquidity Rejection Explainer
- Rejected Candidate Memory Writer
- Rejection Learning Feed

## 12. User Override Tracking Layer

Responsibilities:

- detect user overrides
- record user actions
- track override outcomes
- classify override results
- detect missed opportunities
- detect avoided failures
- analyze user decision quality
- feed override results into learning

Main components:

- User Override Detector
- User Action Recorder
- Override Outcome Tracker
- Override Classification Engine
- Missed Opportunity Detector
- Avoided Correctly Detector
- User Decision Quality Analyzer
- Override Learning Feed

## 13. Memory Layer

Responsibilities:

- store fact memory
- store skill memory
- store case memory
- store user feedback memory
- store user override memory
- store rejection memory
- store action suggestion memory
- store opportunity lifecycle memory
- store do-not-touch memory
- store versioned decision memory
- store vector memory
- store AI response memory
- retrieve relevant memory for decisions

Main components:

- Fact Memory
- Skill Memory
- Case Memory
- User Feedback Memory
- User Override Memory
- Rejection Memory
- Action Suggestion Memory
- Opportunity Lifecycle Memory
- Do-Not-Touch Memory
- Versioned Decision Memory
- Vector Memory
- AI Response Memory
- Memory Retriever

## 14. Learning Layer

Responsibilities:

- track outcomes
- classify failures
- track rejection outcomes
- track action suggestion outcomes
- evaluate opportunity lifecycle behavior
- evaluate do-not-touch rules
- evaluate user overrides
- evaluate skills
- summarize cases
- generate weekly learning reports
- generate improvement suggestions
- support champion/challenger rules
- support future model training

Main components:

- Outcome Tracker
- Failure Classifier
- Rejection Outcome Tracker
- Action Suggestion Outcome Tracker
- Opportunity Lifecycle Evaluator
- Do-Not-Touch Rule Evaluator
- User Override Evaluator
- Skill Evaluator
- Case Summarizer
- Weekly Learning Report Generator
- Improvement Suggestion Engine
- Champion / Challenger Engine
- Model Training Engine

## 15. AI Advisor / Provider Layer

Responsibilities:

- manage AI providers
- support disabled mode
- support manual paste mode
- support free web AI provider
- support Gemini provider
- support Grok provider
- support OpenAI-compatible provider
- support local LLM and Ollama
- support custom provider
- build prompts
- track prompt versions
- parse responses
- validate JSON schema
- provide AI analysis service

Main components:

- AI Provider Manager
- Provider Registry
- Provider Router
- Provider Health Checker
- Provider Cost / Limit Tracker
- Disabled Mode
- Manual Paste Mode
- Free Web AI Provider
- Gemini Provider
- Grok Provider
- OpenAI-Compatible Provider
- Local LLM / Ollama Provider
- Custom Provider
- Prompt Builder
- Prompt Version Registry
- Response Parser
- JSON Schema Validator
- AI Analysis Service

## 16. AI Research Chat Layer

Responsibilities:

- provide in-platform research chat
- build context automatically
- retrieve source records
- store conversation memory
- route answer modes
- support explain mode
- support action plan mode
- support risk review mode
- support decision trace mode
- support counterargument mode
- support similar case mode
- cite sources used
- save chat notes to memory

Main components:

- AI Research Chat Service
- Chat Context Builder
- Chat Source Retriever
- Chat Conversation Memory
- AI Answer Mode Router
- Explain Mode
- Action Plan Mode
- Risk Review Mode
- Decision Trace Mode
- Counterargument Mode
- Similar Case Mode
- Chat Prompt Builder
- Chat Response Parser
- Chat Source Citation Builder
- Chat Note Saver

## 17. Agent Scheduler / Refresh Layer

Responsibilities:

- manage scan schedule
- handle manual refresh
- run market-hours scan job
- run option snapshot job
- run news scan job
- run watchlist news scan job
- run filing scan job
- run earnings calendar refresh
- run IV risk refresh
- run daily recommendation job
- run opportunity lifecycle update
- run next review trigger job
- run do-not-touch release check
- run rejected candidate tracking
- run user override tracking
- run outcome tracking
- run weekly learning
- run model retraining
- log every job run
- report agent status

Main components:

- Scan Schedule Manager
- Manual Refresh Controller
- Market-Hours Scan Job
- Option Snapshot Job
- News Scan Job
- Watchlist News Scan Job
- Filing Scan Job
- Earnings Calendar Refresh Job
- IV Risk Refresh Job
- Daily Recommendation Job
- Opportunity Lifecycle Update Job
- Next Review Trigger Job
- Do-Not-Touch Release Check Job
- Rejected Candidate Tracking Job
- User Override Tracking Job
- Signal Outcome Tracking Job
- Action Suggestion Outcome Tracking Job
- Weekly Learning Job
- Model Retraining Job
- Job Run Logger
- Agent Status Reporter

## 18. Memory Export / Import Layer

Responsibilities:

- export full memory
- export case memory
- export rejection memory
- export action suggestions
- export opportunity lifecycle
- export do-not-touch records
- export user overrides
- export user feedback
- export learning reports
- export versioned decisions
- export vector memory
- generate AI-readable memory summary
- generate system playbook
- validate memory package
- import memory package
- manage schema versions

Main components:

- Full Memory Exporter
- Case Memory Exporter
- Rejection Memory Exporter
- Action Suggestion Exporter
- Opportunity Lifecycle Exporter
- Do-Not-Touch Exporter
- User Override Exporter
- User Feedback Exporter
- Learning Report Exporter
- Versioned Decision Exporter
- Vector Memory Exporter
- AI-Readable Memory Summary Generator
- System Playbook Generator
- Memory Package Validator
- Memory Importer
- Schema Version Manager

## 19. UI Experience / Progressive Disclosure Layer

Responsibilities:

- prioritize visible fields
- build page summaries
- manage expandable details
- support beginner and advanced views
- build one-page ticker brief layout
- prioritize dashboard worklist
- load default UI profile
- prevent UI overload

Main components:

- Field Priority Manager
- Page Summary Builder
- Expandable Detail Panel Manager
- Beginner / Advanced View Switcher
- One-Page Brief Layout Manager
- Dashboard Worklist Prioritizer
- Default Profile UI Loader
- UI Complexity Guard

## 20. Versioning / Governance Layer

Responsibilities:

- track rule versions
- track strategy profile versions
- track model versions
- track prompt versions
- track data schema versions
- build decision version stamps
- check version compatibility
- write audit metadata

Main components:

- Rule Version Registry
- Strategy Profile Version Registry
- Model Version Registry
- Prompt Version Registry
- Data Schema Version Registry
- Decision Version Stamp Builder
- Version Compatibility Checker
- Audit Metadata Writer

## Core Decision Flow

1. Load latest ticker, option, news, earnings, IV, and memory data.
2. Run Data Sufficiency Gate.
3. If data is insufficient, output an insufficient-data action state.
4. Run Hard Filter Gate.
5. Build Stock Thesis Decision.
6. Build Option Expression Decision.
7. Build Event / Earnings / IV Risk Decision.
8. Build Memory Risk Decision.
9. Generate Opportunity Quality Checklist.
10. Calculate Priority Score.
11. Calculate Confidence Score.
12. Build Confidence Score Breakdown.
13. Classify Final Action Label.
14. Build Decision Trace.
15. Attach Version Stamp.
16. Generate Action Suggestion Package.
17. Generate Next Review Trigger.
18. Update Opportunity Lifecycle.
19. Check Do-Not-Touch rules.
20. Detect user override behavior.
21. Add item to Today’s Research Worklist if relevant.
22. Display on Dashboard, Ticker Brief, or AI Chat.
23. Track future outcome.
24. Feed result into Memory and Learning.

## Required Final Output Fields

Normal opportunity output:

- final_action_label
- lifecycle_state
- priority_score
- confidence_score
- confidence_breakdown
- suggested_action_summary
- entry_condition
- option_contract_criteria
- invalidation_condition
- upgrade_condition
- downgrade_condition
- watch_condition
- next_review_trigger
- decision_trace
- version_stamp
- action_items

Insufficient-data output:

- final_action_label
- missing_data_type
- data_freshness_status
- data_quality_reason
- suggested_data_fix
- next_refresh_action
- action_items
