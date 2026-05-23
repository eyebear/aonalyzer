# Decision Flow

Every symbol flows through deterministic layers. Option data is optional at
every step; the stock path never depends on it.

```
DailyPrice / StockSetup / Events / Earnings / IV / (optional) manual option
        │
        ▼
[19] Data Sufficiency Gate
        ├─ price-history / stock-setup insufficiency → BLOCKS stock decision
        └─ missing/insufficient option data → blocks OPTION suitability only (non-blocking warning)
        │
        ▼
[20] Hard Filter Gate
        ├─ stock hard filters (risk/reward, extension, regime, earnings) → always run
        └─ option hard filters → run ONLY when option data exists
        │
        ▼
[21] Decision Intelligence
        stock_thesis × option_expression × instrument_scope × event_risk × memory_risk
        → final_action_label + priority + confidence + checklist + trace + version_stamp
        │
        ▼
[22] Action Suggestion
        → entry / invalidation / upgrade / downgrade / watch / next-review / action items
        │
        ├──► [23] Rejection intelligence (stock-good/option-bad vs option-missing)
        ├──► [24] Do-Not-Touch (never from missing option data alone)
        ├──► [25] Lifecycle state (READY / WATCH / WAIT / WAIT_FOR_MANUAL_OPTION_INPUT / ...)
        ├──► [26] Next-review triggers + review queue
        └──► [27] Today's Research Worklist
```

## Stock-only path (no option data)

1. Sufficiency gate: price history + stock setup sufficient → not blocked.
2. Stock hard filters run; option hard filters are **skipped**.
3. Instrument scope = `STOCK_ONLY`.
4. Final label is one of `READY_TO_RESEARCH_STOCK_ONLY`, `WATCH_STOCK_ONLY`,
   `WAIT_FOR_ENTRY_STOCK_ONLY`, `OPTION_DATA_NOT_AVAILABLE` (stock ready, option
   side requested but unavailable), `NO_TRADE`, or `INSUFFICIENT_PRICE_HISTORY`.

## Option-aware path (manual option pasted)

1. Stock path runs exactly as above.
2. The pasted contract is parsed (no values invented); if enough fields exist,
   option suitability + option hard filters run.
3. Instrument scope becomes `OPTION_AVAILABLE` or `OPTION_REJECTED`.
4. Final label may become `READY_TO_RESEARCH_WITH_OPTION` or
   `STOCK_OK_OPTION_BAD` (stock thesis valid but the option failed suitability).

## Memory & versioning

- Memory risk (case memory) feeds confidence/priority/warnings only — it never
  changes the deterministic final label.
- Every persisted decision carries eight version keys (rule, model, prompt,
  option_parser, strategy_profile, data_schema, decision_engine,
  action_suggestion) and an audit row in `decision_audit_metadata`.
