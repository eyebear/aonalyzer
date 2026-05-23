# Action Label Guide

The final action label is the user-facing verdict produced by the decision
layer. It maps deterministically from the stock thesis and the
instrument scope.

| Label | Meaning | Option data? |
|-------|---------|--------------|
| `READY_TO_RESEARCH_STOCK_ONLY` | Stock thesis is ready; research the stock now. | not requested / not needed |
| `READY_TO_RESEARCH_WITH_OPTION` | Stock thesis ready and a pasted option passed suitability. | present, suitable |
| `STOCK_OK_OPTION_BAD` | Stock thesis is valid but the pasted option failed suitability. | present, rejected |
| `OPTION_DATA_NOT_AVAILABLE` | Stock thesis ready; option analysis requested but no option data is available — paste a contract. | requested, missing |
| `WATCH_STOCK_ONLY` | Worth watching; not an entry yet. | n/a |
| `WAIT_FOR_ENTRY_STOCK_ONLY` | Thesis valid but price is outside the entry zone. | n/a |
| `NO_TRADE` | Hard filters or thesis rule out the setup. | n/a |
| `INSUFFICIENT_PRICE_HISTORY` | Not enough price history to form a stock thesis. | n/a |

## Instrument scope

- `STOCK_ONLY` — only the stock side was evaluated.
- `OPTION_AVAILABLE` — a manual option contract was evaluated and is suitable.
- `OPTION_REJECTED` — a manual option contract was evaluated and failed filters.

## Lifecycle states

`READY_FOR_RESEARCH`, `WATCHING`, `WAITING_FOR_ENTRY`,
`WAIT_FOR_MANUAL_OPTION_INPUT`, `REJECTED`, `INSUFFICIENT_DATA`.

## Key rule

`OPTION_DATA_NOT_AVAILABLE` and `STOCK_OK_OPTION_BAD` both mean the **stock**
thesis is valid — they are research opportunities, not rejections. Only
`NO_TRADE` and `INSUFFICIENT_PRICE_HISTORY` are stock-blocked.
