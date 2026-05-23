"""Phases 41-45 — case memory, vector memory, skills, learning reports,
improvement engine + champion/challenger.

Protects: case creation from real outcomes (incl. stock-right/option-wrong and
stock-right/option-missing), deterministic vector retrieval, skill metrics,
report contents, approval-gated improvements, and that vector memory feeding
the decision layer never changes the deterministic label.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.action.action_models import ActionSuggestion
from app.database.base import Base
from app.database.models import DailyPrice
from app.learning.champion_challenger import RuleArm, compare_rule_versions
from app.learning.improvement_engine import ImprovementEngine
from app.learning.improvement_models import STATUS_APPROVED, STATUS_PROPOSED
from app.learning.learning_report_service import LearningReportService
from app.learning.signal_outcome_service import SignalOutcomeService
from app.memory.case_memory_models import (
    CASE_STOCK_RIGHT_OPTION_MISSING,
    CaseMemory,
)
from app.memory.case_memory_service import CaseMemoryService
from app.memory.embedding_service import (
    cosine_similarity,
    deterministic_embedding,
)
from app.memory.skill_service import SkillService
from app.memory.vector_search_service import VectorSearchService
from app.quant.stock_setup_models import StockSetup

_engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
)
_TestSession = sessionmaker(bind=_engine, autoflush=False, autocommit=False)
SIGNAL_DATE = date(2026, 3, 2)


@pytest.fixture(autouse=True)
def reset_db():
    Base.metadata.drop_all(bind=_engine)
    with _engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS manual_option_snapshots"))
    Base.metadata.create_all(bind=_engine)
    yield


def _seed_rising_prices(symbol: str, n: int = 40) -> None:
    session = _TestSession()
    try:
        for i in range(n):
            close = 100.0 + i * 3.0  # rises steeply -> target (110) hit within horizon
            session.add(
                DailyPrice(
                    symbol=symbol,
                    price_date=SIGNAL_DATE + timedelta(days=i),
                    open_price=close - 0.5,
                    high_price=close + 1.0,
                    low_price=close - 1.0,
                    close_price=close,
                    volume=1_000_000 + i,
                    source="test",
                )
            )
        session.commit()
    finally:
        session.close()


def _seed_setup(symbol: str) -> None:
    session = _TestSession()
    try:
        session.add(
            StockSetup(
                symbol=symbol,
                snapshot_date=SIGNAL_DATE,
                source="test",
                source_record_count=60,
                current_close=100.0,
                nearest_support=95.0,
                nearest_resistance=130.0,
                sma_50=98.0,
                atr_14=2.0,
                direction="LONG",
                stop_method="ATR",
                target_price=110.0,
                stop_price=95.0,
                risk_per_share=5.0,
                reward_per_share=10.0,
                stock_risk_reward=2.0,
                entry_zone_low=95.0,
                entry_zone_high=102.0,
                data_sufficiency_status="SUFFICIENT",
            )
        )
        session.add(
            ActionSuggestion(
                symbol=symbol,
                snapshot_date=SIGNAL_DATE,
                final_action_label="READY_TO_RESEARCH_STOCK_ONLY",
                instrument_scope="STOCK_ONLY",
                lifecycle_state="READY_FOR_RESEARCH",
                option_expression_status="OPTION_EXPR_NOT_EVALUATED",
                suggested_action_summary="x",
            )
        )
        session.commit()
    finally:
        session.close()


# --- embedding -------------------------------------------------------------


def test_deterministic_embedding_is_reproducible() -> None:
    a = deterministic_embedding("AMD pullback long target hit")
    b = deterministic_embedding("AMD pullback long target hit")
    assert a == b
    assert cosine_similarity(a, b) == pytest.approx(1.0)


def test_cosine_similarity_orders_related_text_higher() -> None:
    q = deterministic_embedding("breakout retest long setup")
    near = deterministic_embedding("breakout retest long setup confirmed")
    far = deterministic_embedding("earnings iv crush risk high")
    assert cosine_similarity(q, near) > cosine_similarity(q, far)


# --- case memory -----------------------------------------------------------


def test_case_memory_stock_right_option_missing() -> None:
    _seed_rising_prices("AMD")
    _seed_setup("AMD")
    session = _TestSession()
    try:
        SignalOutcomeService(horizons=(5,)).run(session)
        result = CaseMemoryService().build_cases(session)
        assert result.cases_created >= 1
        cases = session.query(CaseMemory).all()
        # Stock hit target with no option data -> stock-right/option-missing.
        assert any(c.case_type == CASE_STOCK_RIGHT_OPTION_MISSING for c in cases)
        # Re-running does not duplicate (source-keyed upsert + fed flag).
        result2 = CaseMemoryService().build_cases(session)
        assert result2.cases_created == 0
    finally:
        session.close()


# --- vector memory ---------------------------------------------------------


def test_vector_ingest_and_search() -> None:
    _seed_rising_prices("AMD")
    _seed_setup("AMD")
    session = _TestSession()
    try:
        SignalOutcomeService(horizons=(5,)).run(session)
        CaseMemoryService().build_cases(session)
        vs = VectorSearchService()
        vs.ingest_all(session)
        results = vs.search(session, query_text="AMD stock right option missing", limit=5)
        assert results
        assert results[0]["similarity"] >= results[-1]["similarity"]
    finally:
        session.close()


def test_vector_memory_does_not_change_deterministic_label() -> None:
    """Memory feeds confidence/priority but never the final label."""
    _seed_rising_prices("AMD")
    _seed_setup("AMD")
    session = _TestSession()
    try:
        from app.decision.decision_service import DecisionService

        before = DecisionService().evaluate_symbol(session, "AMD", persist=False).decision
        # Build memory + cases, then re-evaluate.
        SignalOutcomeService(horizons=(5,)).run(session)
        CaseMemoryService().build_cases(session)
        after = DecisionService().evaluate_symbol(session, "AMD", persist=False).decision
        assert before.final_label == after.final_label
    finally:
        session.close()


# --- skills ----------------------------------------------------------------


def test_skill_metrics_computed() -> None:
    _seed_rising_prices("AMD")
    _seed_setup("AMD")
    session = _TestSession()
    try:
        SignalOutcomeService(horizons=(5,)).run(session)
        svc = SkillService()
        svc.register_initial_skills(session)
        assert len(svc.list_skills(session)) == 9
        svc.infer_and_link(session)
        result = svc.compute_performance(session)
        assert result.skills == 9
        perf = svc.latest_performance(session)
        assert len(perf) == 9
    finally:
        session.close()


# --- learning reports ------------------------------------------------------


def test_learning_report_reports_missing_option_as_missing() -> None:
    _seed_rising_prices("AMD")
    _seed_setup("AMD")
    session = _TestSession()
    try:
        SignalOutcomeService(horizons=(5,)).run(session)
        result = LearningReportService().generate_weekly_report(
            session, period_end=SIGNAL_DATE + timedelta(days=3)
        )
        summary = result.report.summary_json
        assert "signals" in summary
        assert summary["manual_option_input_usage"]["signals_with_option_outcome"] == 0
        assert "missing" in summary["manual_option_input_usage"]["note"].lower()
    finally:
        session.close()


# --- improvement engine + champion/challenger ------------------------------


def test_improvement_engine_approval_gated() -> None:
    session = _TestSession()
    try:
        # Seed enough stock-right/option-wrong cases to trigger a suggestion.
        for i in range(6):
            session.add(
                CaseMemory(
                    symbol=f"S{i}",
                    case_type="STOCK_RIGHT_OPTION_WRONG",
                    source_type="SIGNAL_OUTCOME",
                    source_id=i,
                    outcome_type="STOCK_RIGHT_OPTION_WRONG",
                    option_data_available=True,
                    lesson_summary="x",
                )
            )
        session.commit()
        engine = ImprovementEngine()
        result = engine.generate(session)
        assert result.suggestions_created >= 1
        proposed = engine.list_suggestions(session, status=STATUS_PROPOSED)
        assert proposed
        # Approval is explicit and does not auto-apply anything.
        decided = engine.decide(session, proposed[0].id, approve=True, decided_by="tester")
        assert decided.status == STATUS_APPROVED
    finally:
        session.close()


def test_champion_challenger_insufficient_evidence_safe() -> None:
    session = _TestSession()
    try:
        result = compare_rule_versions(
            session,
            champion=RuleArm(name="c", min_risk_reward=2.0),
            challenger=RuleArm(name="ch", min_risk_reward=1.7),
        )
        # No outcomes -> safe recommendation, no rule change.
        assert result.recommendation == "INSUFFICIENT_EVIDENCE"
    finally:
        session.close()
