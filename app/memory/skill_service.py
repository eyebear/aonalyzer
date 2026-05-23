"""Phase 43, steps 43.4-43.10 — skill registration, linking, and metrics.

Registers the initial skills, links decisions to the skills that contributed
(from setup type + available option/IV/event data), and computes performance
metrics from recorded signal outcomes and case memory. Metrics are recorded and
exposed only — skill behavior is never silently altered by them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.common.service_utils import ensure_tables
from app.learning.signal_outcome_models import (
    OPTION_OUTCOME_ESTIMATED,
    SignalOutcome,
)
from app.memory.case_memory_models import (
    CASE_STOCK_RIGHT_OPTION_WRONG,
    CaseMemory,
)
from app.memory.skill_models import (
    SkillLink,
    SkillPerformance,
    SkillRegistry,
    SkillVersion,
)
from app.setup_detection.setup_detection_models import StockSetupSignal

# Phase 43.4 — initial skills (name, category, description).
INITIAL_SKILLS: list[tuple[str, str, str]] = [
    ("PULLBACK_LONG_SETUP", "SETUP", "Detects healthy pullback long setups."),
    ("BREAKOUT_RETEST_LONG_SETUP", "SETUP", "Detects breakout/retest long setups."),
    ("MANUAL_OPTION_TEXT_READER", "OPTION", "Reads pasted free-form option text."),
    ("OPTION_SUITABILITY_CHECK", "OPTION", "Checks option contract suitability."),
    ("BREAKEVEN_REALITY_CHECK", "OPTION", "Checks target vs breakeven reality."),
    ("IV_RISK_FILTER", "RISK", "Filters out over-expensive / high-IV options."),
    ("PRICE_IN_ANALYSIS", "EVENT", "Assesses whether news is already priced in."),
    (
        "STOCK_RIGHT_OPTION_WRONG_ANALYZER",
        "LEARNING",
        "Analyzes the stock-right/option-wrong failure pattern.",
    ),
    ("SECTOR_STRENGTH_CONFIRMATION", "SETUP", "Confirms setups with sector strength."),
]

# Setup type -> setup skill.
_SETUP_SKILL_BY_TYPE = {
    "PULLBACK_LONG": "PULLBACK_LONG_SETUP",
    "BREAKOUT_RETEST_LONG": "BREAKOUT_RETEST_LONG_SETUP",
    "SECTOR_STRENGTH_LONG": "SECTOR_STRENGTH_CONFIRMATION",
}
_OPTION_SKILLS = (
    "MANUAL_OPTION_TEXT_READER",
    "OPTION_SUITABILITY_CHECK",
    "BREAKEVEN_REALITY_CHECK",
)


@dataclass
class SkillComputeResult:
    skills: int = 0
    performances_written: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {"skills": self.skills, "performances_written": self.performances_written}


class SkillService:
    def __init__(self) -> None:
        pass

    def ensure_tables(self, db: Session) -> None:
        ensure_tables(db)

    # ----------------------------------------------------------- registration

    def register_initial_skills(self, db: Session) -> int:
        self.ensure_tables(db)
        created = 0
        for name, category, description in INITIAL_SKILLS:
            exists = (
                db.query(SkillRegistry)
                .filter(SkillRegistry.skill_name == name)
                .one_or_none()
            )
            if exists is None:
                db.add(
                    SkillRegistry(
                        skill_name=name, category=category, description=description
                    )
                )
                db.add(
                    SkillVersion(
                        skill_name=name,
                        version="1.0",
                        is_current=True,
                        definition_json={"category": category},
                    )
                )
                created += 1
        db.commit()
        return created

    def list_skills(self, db: Session) -> list[SkillRegistry]:
        self.ensure_tables(db)
        return db.query(SkillRegistry).order_by(SkillRegistry.skill_name.asc()).all()

    # --------------------------------------------------------------- linking

    def link_skill(
        self,
        db: Session,
        *,
        skill_name: str,
        symbol: str,
        snapshot_date,
        source_type: str | None = None,
    ) -> bool:
        existing = (
            db.query(SkillLink)
            .filter(SkillLink.skill_name == skill_name)
            .filter(SkillLink.symbol == symbol)
            .filter(SkillLink.snapshot_date == snapshot_date)
            .one_or_none()
        )
        if existing is not None:
            return False
        db.add(
            SkillLink(
                skill_name=skill_name,
                symbol=symbol,
                snapshot_date=snapshot_date,
                source_type=source_type,
            )
        )
        return True

    def infer_and_link(self, db: Session, *, limit: int = 1000) -> int:
        """Phase 43.5 — link decisions to the skills that contributed."""
        self.ensure_tables(db)
        linked = 0
        signals = db.query(StockSetupSignal).limit(limit).all()
        for sig in signals:
            skill = _SETUP_SKILL_BY_TYPE.get((sig.setup_type or "").upper())
            if skill:
                linked += int(
                    self.link_skill(
                        db,
                        skill_name=skill,
                        symbol=sig.symbol,
                        snapshot_date=sig.snapshot_date,
                        source_type="STOCK_SETUP_SIGNAL",
                    )
                )
            if sig.sector_symbol:
                linked += int(
                    self.link_skill(
                        db,
                        skill_name="SECTOR_STRENGTH_CONFIRMATION",
                        symbol=sig.symbol,
                        snapshot_date=sig.snapshot_date,
                        source_type="SECTOR",
                    )
                )

        # Option skills: any symbol/date that has a manual option snapshot uses
        # the option reader / suitability / breakeven skills.
        for outcome in db.query(SignalOutcome).limit(limit).all():
            if outcome.option_outcome_status == OPTION_OUTCOME_ESTIMATED:
                for skill in _OPTION_SKILLS:
                    linked += int(
                        self.link_skill(
                            db,
                            skill_name=skill,
                            symbol=outcome.symbol,
                            snapshot_date=outcome.signal_date,
                            source_type="MANUAL_OPTION",
                        )
                    )

        # Stock-right/option-wrong analyzer links from case memory.
        for case in (
            db.query(CaseMemory)
            .filter(CaseMemory.case_type == CASE_STOCK_RIGHT_OPTION_WRONG)
            .limit(limit)
            .all()
        ):
            if case.snapshot_date is not None:
                linked += int(
                    self.link_skill(
                        db,
                        skill_name="STOCK_RIGHT_OPTION_WRONG_ANALYZER",
                        symbol=case.symbol,
                        snapshot_date=case.snapshot_date,
                        source_type="CASE_MEMORY",
                    )
                )
        db.commit()
        return linked

    # ------------------------------------------------------------- metrics

    def compute_performance(self, db: Session) -> SkillComputeResult:
        """Phase 43.6-43.10 — compute and persist per-skill metrics."""
        self.ensure_tables(db)
        result = SkillComputeResult()
        for skill in self.list_skills(db):
            result.skills += 1
            metrics = self._metrics_for_skill(db, skill.skill_name)
            db.add(
                SkillPerformance(
                    skill_name=skill.skill_name,
                    skill_version="1.0",
                    **metrics,
                )
            )
            result.performances_written += 1
        db.commit()
        return result

    def _metrics_for_skill(self, db: Session, skill_name: str) -> dict[str, Any]:
        links = (
            db.query(SkillLink).filter(SkillLink.skill_name == skill_name).all()
        )
        keys = {(link.symbol, link.snapshot_date) for link in links}
        if not keys:
            return {
                "sample_size": 0,
                "target_hit_rate": None,
                "stop_first_rate": None,
                "stock_right_option_wrong_rate": None,
                "manual_option_reader_usefulness": None,
                "expected_value_proxy": None,
                "context_json": {"linked_keys": 0},
            }

        outcomes = [
            o
            for o in db.query(SignalOutcome).all()
            if (o.symbol, o.signal_date) in keys and o.price_data_available
        ]
        sample = len(outcomes)
        target_hits = sum(1 for o in outcomes if o.target_hit)
        stop_hits = sum(1 for o in outcomes if o.stop_hit)
        returns = [o.stock_return_pct for o in outcomes if o.stock_return_pct is not None]
        option_estimated = [
            o for o in outcomes if o.option_outcome_status == OPTION_OUTCOME_ESTIMATED
        ]
        option_useful = sum(
            1
            for o in option_estimated
            if o.option_return_pct is not None and o.option_return_pct > 0
        )

        cases = [
            c
            for c in db.query(CaseMemory).all()
            if (c.symbol, c.snapshot_date) in keys
        ]
        srow_cases = sum(
            1 for c in cases if c.case_type == CASE_STOCK_RIGHT_OPTION_WRONG
        )

        def _rate(num: int, denom: int) -> float | None:
            return round(num / denom, 4) if denom else None

        return {
            "sample_size": sample,
            "target_hit_rate": _rate(target_hits, sample),
            "stop_first_rate": _rate(stop_hits, sample),
            "stock_right_option_wrong_rate": _rate(srow_cases, len(cases)),
            "manual_option_reader_usefulness": _rate(
                option_useful, len(option_estimated)
            ),
            "expected_value_proxy": round(sum(returns) / len(returns), 4)
            if returns
            else None,
            "context_json": {"linked_keys": len(keys), "outcomes": sample},
        }

    def latest_performance(self, db: Session) -> list[SkillPerformance]:
        self.ensure_tables(db)
        rows = (
            db.query(SkillPerformance)
            .order_by(SkillPerformance.computed_at.desc(), SkillPerformance.id.desc())
            .all()
        )
        seen: set[str] = set()
        latest: list[SkillPerformance] = []
        for row in rows:
            if row.skill_name not in seen:
                seen.add(row.skill_name)
                latest.append(row)
        return latest


__all__ = ["INITIAL_SKILLS", "SkillComputeResult", "SkillService"]
