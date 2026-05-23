# Screenshots

> Screenshots are captured from the running dashboard, not committed as binaries
> in this repository. Start the stack and capture each page below. (Generated
> image files are intentionally kept out of the repo / handoff.)

## How to capture

```bash
docker compose up --build        # or: streamlit run app/dashboard/main.py
# open http://localhost:8501 and screenshot each page from the sidebar
```

## Pages to capture

| Page | What it shows |
|------|---------------|
| Home | Today's Research Worklist (first), agent status, manual refresh, risk alerts, market regime, recent events, experience warnings |
| Daily Opportunities | Action-labeled candidate cards with priority/confidence and option-data warnings |
| Ticker Analyzer | One-Page Brief, action panel, manual option input flow |
| Manual Option Review | Pasted option snapshots, liquidity, IV/Greeks, breakeven, suitability |
| Earnings / IV Risk | Next earnings, days-to-earnings, IV state (honest about missing IV), IV crush |
| News / Events | Filtered event browser with source links and reviewed flags |
| Settings | Profiles, schedule, risk filters, manual option behavior |
| Memory Cases | Reusable lessons + vector search |
| Learning Reports | Weekly summary + approval-gated improvement suggestions |

Each page is built with progressive disclosure: beginner mode keeps it lean,
advanced mode reveals traces, confidence breakdowns, and version stamps.
