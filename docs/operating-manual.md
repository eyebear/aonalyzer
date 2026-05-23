# Operating Manual

Aonalyzer is a local, research and decision-support platform. It is **not** an
auto-trading system and it is **not** broker-connected. It produces actionable
research suggestions; you make and place all trades yourself.

## Daily workflow

1. **Open Home.** The Home page (`streamlit run app/dashboard/main.py`) opens on
   Today's Research Worklist — your prioritized daily tasks. Click *Generate /
   refresh worklist* to rebuild it from the latest analysis.
2. **Work the worklist top-down.** Items are ranked by priority then type:
   risk alerts → due reviews → ready actions → paste-option prompts →
   wait/watch → events → experience warnings.
3. **Refresh data as needed** with the manual refresh buttons (market data,
   news, earnings, IV) or per-ticker on the Ticker Analyzer page.
4. **Review opportunities** on the Daily Opportunities page. Each card shows the
   final action label, instrument scope, suggested action, priority/confidence,
   the main option-data warning (if any), the next review trigger, and action
   items.
5. **Analyze a ticker** on the Ticker Analyzer page: read the One-Page Brief,
   review the action panel, and — optionally — paste a manual option contract to
   enable option suitability analysis.
6. **Ask the AI** on the AI Research Chat page (Explain / Action Plan / Risk
   Review / Decision Trace / Counterargument / Similar Case / Option Text
   Reader). The chat uses only system context and never invents option values.
7. **Record what you did** with the feedback buttons (review / watch / reject /
   manual trade). Overrides are stored and classified later from real outcomes.
8. **Let outcomes accumulate.** After-close jobs track 5/10/20/30-day returns,
   rejection/freeze outcomes, build case memory, and (weekly) a learning report.

## The non-blocking option contract

- Missing option data **never** blocks stock-only research.
- Incomplete option data blocks **only** option suitability.
- The system **never** invents missing option values.
- A `PASTE_OPTION_DATA` worklist item appears only when the stock thesis is valid
  but the option side cannot be evaluated — never for a stock-blocked candidate.

## Pages

| Page | Purpose |
|------|---------|
| Home | Worklist-first command center, refresh, risk alerts, regime, events |
| Daily Opportunities | Action-labeled research candidates |
| Rejected But Interesting | Rejected/partial candidates worth watching |
| Do-Not-Touch | Active risk freezes + release conditions |
| Ticker Analyzer | Manual ticker workflow + manual option input |
| Manual Option Review | Pasted option snapshots + suitability |
| Earnings / IV Risk | Earnings timing + IV risk (honest about missing IV) |
| News / Events | Event browser with filters + reviewed flag |
| AI Research Chat | Context-grounded chat with seven answer modes |
| User Override History | Your actions vs system suggestions + outcomes |
| Signal History | Forward outcomes of past recommendations |
| Rejection History | Whether past rejections/freezes were useful |
| Memory Cases | Reusable lessons from real outcomes |
| Skills | Skill performance metrics |
| Learning Reports | Weekly summaries + approval-gated improvements |
| Settings | Profiles, schedule, risk filters, manual option behavior |
| Memory Export / Import | Back up / restore learned memory |
