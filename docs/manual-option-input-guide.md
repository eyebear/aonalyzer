# Manual Option Input Guide

Aonalyzer has **no live broker option-chain feed**. Option analysis is fully
user-driven: you copy option data from a website or broker and paste it in. The
parser extracts what it can and shows missing fields honestly — it never invents
values.

## What to paste

Paste free-form text that includes as many of these as you have:

- symbol, expiration, strike, call/put
- bid, ask, last
- implied volatility (IV)
- delta, gamma, theta, vega
- volume, open interest

Example:

```
AMD June 19 2026 170 call, stock around 165.20, bid 8.20 ask 8.80, last 8.50,
IV around 42.5%, delta .48, gamma .025, theta -.09, vega .31, volume 1200, OI 5400.
```

## Where to paste

- **Ticker Analyzer page** → *Manual Option Input* → *Parse Option Text*.
- **Home / Manual Option Review page** → the *Paste / Analyze Option Data* shortcut.
- **API**: `POST /api/options/manual-input` or `POST /api/tickers/{symbol}/options/manual-input` with `{"raw_text": "..."}`.

## What happens

1. **Parse** extracts available fields, computes DTE, mid, spread %, contract
   cost, breakeven, and breakeven distance — only when the inputs exist.
   `data_quality_status` is `OPTION_TEXT_PARSED`, `INSUFFICIENT_OPTION_DATA`, or
   `OPTION_DATA_NOT_AVAILABLE`. Missing fields are listed explicitly.
3. **Analyze with AI** (optional) produces a plain-English explanation. It never
   fabricates missing numbers.
4. **Suitability** runs only when enough fields exist (Phase 15): DTE, premium,
   spread, OI, volume, IV, breakeven, and target-vs-breakeven checks.

## Honesty rules

- Incomplete option data blocks option suitability only — the stock thesis is
  unaffected.
- The AI Option Text Reader and the chat both state which fields are missing and
  never invent them.
- `strict_option_parser_mode` (Settings) can require more fields before a parse
  is treated as usable. `option_text_ai_reader_enabled` toggles the AI reader.
