"""Phase 49 — full local end-to-end orchestration pipeline.

Runs the complete local research flow over the watchlist (or given symbols):
market/news/earnings-IV/technical refresh (best-effort, recorded as agent
runs), the non-blocking manual-option step, optional option suitability,
decisions, action suggestions, lifecycle/review updates, worklist generation,
and memory updates — then validates dashboard data availability.

Hard contract: the pipeline must NEVER fail because option data is missing, and
it is safe to run repeatedly (every persisting step is idempotent/upsert).
Each step is isolated so one step's failure does not abort the run.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.action.action_service import ActionSuggestionService
from app.agent.manual_refresh_controller import manual_refresh_controller
from app.common.service_utils import ensure_tables, load_watchlist_symbols
from app.decision.decision_service import DecisionService
from app.learning.rejection_outcome_service import RejectionOutcomeService
from app.learning.signal_outcome_service import SignalOutcomeService
from app.lifecycle.lifecycle_service import LifecycleService
from app.memory.case_memory_service import CaseMemoryService
from app.options.manual_option_input_service import ManualOptionInputService
from app.options.option_suitability_service import OptionSuitabilityService
from app.quant.stock_setup_models import StockSetup
from app.review.review_service import ReviewService
from app.worklist.today_worklist_service import TodayWorklistService


@dataclass
class StepResult:
    name: str
    status: str
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "status": self.status, "detail": self.detail}


@dataclass
class PipelineResult:
    started_at: str
    finished_at: str
    symbols: list[str]
    steps: list[StepResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "symbols": list(self.symbols),
            "steps": [s.to_dict() for s in self.steps],
        }


class FullPipeline:
    def __init__(self) -> None:
        self.decision_service = DecisionService()
        self.action_service = ActionSuggestionService(decision_service=self.decision_service)
        self.lifecycle_service = LifecycleService()
        self.review_service = ReviewService()
        self.worklist_service = TodayWorklistService()
        self.signal_service = SignalOutcomeService()
        self.rejection_service = RejectionOutcomeService()
        self.case_service = CaseMemoryService()
        self.manual_option_service = ManualOptionInputService()
        self.option_suitability_service = OptionSuitabilityService()

    def ensure_tables(self, db: Session) -> None:
        ensure_tables(db)

    def run(
        self,
        db: Session,
        *,
        symbols: list[str] | None = None,
        worklist_date: date | None = None,
        now: datetime | None = None,
    ) -> PipelineResult:
        self.ensure_tables(db)
        now = now or datetime.now(timezone.utc)
        target_symbols = self._resolve_symbols(db, symbols)

        result = PipelineResult(
            started_at=now.isoformat(),
            finished_at=now.isoformat(),
            symbols=target_symbols,
        )

        # 49.2-49.6 — best-effort refresh steps (recorded as agent runs).
        for step_name, fn in (
            ("market_refresh", manual_refresh_controller.refresh_market_data),
            ("news_events", manual_refresh_controller.refresh_news),
            ("earnings_iv", manual_refresh_controller.refresh_earnings),
            ("technical_analysis", manual_refresh_controller.refresh_technical),
        ):
            result.steps.append(self._safe(step_name, lambda fn=fn: {"recorded": bool(fn(db))}))

        # 49.3 — manual option step: non-blocking (no fetch; manual workflow).
        result.steps.append(
            StepResult(
                name="manual_option_snapshot",
                status="OK",
                detail={"note": "Manual option workflow is user-driven and non-blocking."},
            )
        )

        # Per-symbol analysis.
        suitability_runs = 0
        decisions = 0
        actions = 0
        for symbol in target_symbols:
            # 49.7 — optional option suitability only when manual data exists.
            try:
                snaps = self.manual_option_service.list_manual_snapshots(
                    db=db, symbol=symbol, limit=1
                )
                if snaps:
                    self.option_suitability_service.evaluate_snapshot(
                        db=db, snapshot_id=snaps[0].id, option_input_requested=True
                    )
                    suitability_runs += 1
            except Exception:
                pass

            # 49.8 — decision (never blocked by missing option data).
            try:
                self.decision_service.evaluate_symbol(db=db, symbol=symbol, persist=True)
                decisions += 1
            except Exception:
                pass

            # 49.9 — action suggestion.
            try:
                self.action_service.evaluate_symbol(db=db, symbol=symbol, persist=True)
                actions += 1
            except Exception:
                pass

        result.steps.append(
            StepResult(
                "option_suitability",
                "OK",
                {"symbols_with_option_data": suitability_runs},
            )
        )
        result.steps.append(StepResult("decisions", "OK", {"count": decisions}))
        result.steps.append(StepResult("action_suggestions", "OK", {"count": actions}))

        # 49.10 — lifecycle + review updates.
        result.steps.append(
            self._safe(
                "lifecycle_update",
                lambda: {
                    "evaluated": len(
                        self.lifecycle_service.evaluate_many(db=db, symbols=target_symbols)
                    )
                },
            )
        )
        result.steps.append(
            self._safe(
                "review_triggers",
                lambda: self.review_service.run_triggers(db=db, symbols=target_symbols).to_dict(),
            )
        )

        # 49.11 — worklist generation.
        result.steps.append(
            self._safe(
                "worklist",
                lambda: self.worklist_service.generate_worklist(
                    db=db, worklist_date=worklist_date, symbols=target_symbols
                ).to_dict(),
            )
        )

        # 49.12 — memory update (outcomes -> cases), where due.
        result.steps.append(
            self._safe("signal_outcomes", lambda: self.signal_service.run(db=db).to_dict())
        )
        result.steps.append(
            self._safe("rejection_outcomes", lambda: self.rejection_service.run(db=db).to_dict())
        )
        result.steps.append(
            self._safe("case_memory", lambda: self.case_service.build_cases(db=db).to_dict())
        )

        # 49.13 — dashboard validation (data is queryable).
        result.steps.append(
            self._safe("dashboard_validation", lambda: self._validate_dashboard(db))
        )

        result.finished_at = datetime.now(timezone.utc).isoformat()
        return result

    # ---------------------------------------------------------------- helpers

    def _resolve_symbols(self, db: Session, symbols: list[str] | None) -> list[str]:
        if symbols:
            return [s.strip().upper() for s in symbols if s and s.strip()]
        watchlist = load_watchlist_symbols(db)
        if watchlist:
            return watchlist
        # Fallback: symbols that already have a stock setup.
        try:
            rows = db.query(StockSetup.symbol).distinct().all()
            return sorted({r[0] for r in rows})
        except Exception:
            return []

    def _safe(self, name: str, fn) -> StepResult:
        try:
            detail = fn() or {}
            if not isinstance(detail, dict):
                detail = {"result": detail}
            return StepResult(name=name, status="OK", detail=detail)
        except Exception as exc:  # isolate step failure
            return StepResult(name=name, status="ERROR", detail={"error": str(exc)})

    def _validate_dashboard(self, db: Session) -> dict[str, Any]:
        from app.action.action_models import ActionSuggestion
        from app.worklist.worklist_models import ResearchWorklistItem

        return {
            "action_suggestions": db.query(ActionSuggestion).count(),
            "worklist_items": db.query(ResearchWorklistItem).count(),
        }


__all__ = ["FullPipeline", "PipelineResult", "StepResult"]
