"""Phase 21, step 21.6 — Opportunity checklist.

A flat PASS / WARNING / FAIL / SKIPPED list of named checks built from
the Phase 19 sufficiency gate, the Phase 20 hard-filter gate, the event-
risk and memory-risk sub-decisions, and the stock-thesis verdict.

The checklist is the single shape downstream UIs render. Every item is
deterministic from its inputs; nothing here re-evaluates the upstream
logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.data_quality.data_sufficiency_gate import (
    OPTION_DATA_NOT_AVAILABLE as SUFFICIENCY_OPTION_NOT_AVAILABLE,
)
from app.data_quality.data_sufficiency_gate import (
    OPTION_OK as SUFFICIENCY_OPTION_OK,
)
from app.data_quality.data_sufficiency_gate import (
    GateDecision as SufficiencyDecision,
)
from app.data_quality.data_sufficiency_labels import DataSufficiencyLabel
from app.decision.decision_labels import (
    CHECK_FAIL,
    CHECK_PASS,
    CHECK_SKIPPED,
    CHECK_WARNING,
    RISK_HIGH,
    RISK_MEDIUM,
    RISK_UNKNOWN,
)
from app.decision.event_risk_decision import EventRiskDecision
from app.decision.memory_risk_decision import MemoryRiskDecision
from app.hard_filter.hard_filter_gate import HardFilterDecision
from app.options.option_filters import FAIL, PASS, SKIPPED, WARN


@dataclass(frozen=True)
class ChecklistItem:
    name: str
    status: str
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "status": self.status, "detail": self.detail}


def build_opportunity_checklist(
    sufficiency: SufficiencyDecision,
    hard_filter: HardFilterDecision,
    event_risk: EventRiskDecision,
    memory_risk: MemoryRiskDecision,
) -> list[ChecklistItem]:
    items: list[ChecklistItem] = []

    blocking = set(sufficiency.blocking_labels or [])
    non_blocking = set(sufficiency.non_blocking_labels or [])
    reducers = set(sufficiency.confidence_reducers or [])

    # ----- Data sufficiency rows ------------------------------------------
    items.append(
        _item(
            "price_history_sufficient",
            DataSufficiencyLabel.INSUFFICIENT_PRICE_HISTORY.value not in blocking,
            CHECK_FAIL,
            pass_detail="Daily price history is sufficient.",
            fail_detail="Insufficient daily price history.",
        )
    )
    setup_blocking = (
        DataSufficiencyLabel.INSUFFICIENT_STOCK_SETUP_DATA.value in blocking
        or DataSufficiencyLabel.INSUFFICIENT_SETUP_DATA.value in blocking
    )
    items.append(
        ChecklistItem(
            name="stock_setup_defined",
            status=CHECK_FAIL if setup_blocking else CHECK_PASS,
            detail=(
                "Stock setup math is undefined."
                if setup_blocking
                else "Stock setup math is defined."
            ),
        )
    )

    news_status, news_detail = _three_state_status(
        DataSufficiencyLabel.INSUFFICIENT_NEWS_DATA.value,
        blocking,
        non_blocking,
        pass_detail="News data is sufficient.",
        warn_detail="News data is insufficient (non-blocking).",
        fail_detail="News data is insufficient and required by profile.",
    )
    items.append(ChecklistItem("news_data", news_status, news_detail))

    iv_status, iv_detail = _three_state_status(
        DataSufficiencyLabel.INSUFFICIENT_IV_DATA.value,
        blocking,
        non_blocking,
        pass_detail="IV history is sufficient.",
        warn_detail="IV history is insufficient (non-blocking).",
        fail_detail="IV history is insufficient and required by profile.",
    )
    items.append(ChecklistItem("iv_history_data", iv_status, iv_detail))

    earnings_status, earnings_detail = _three_state_status(
        DataSufficiencyLabel.INSUFFICIENT_EARNINGS_DATA.value,
        blocking,
        non_blocking,
        pass_detail="Earnings calendar data is sufficient.",
        warn_detail="Earnings calendar data is insufficient (non-blocking).",
        fail_detail="Earnings calendar data is insufficient and required by profile.",
    )
    items.append(ChecklistItem("earnings_data", earnings_status, earnings_detail))

    memory_label = DataSufficiencyLabel.INSUFFICIENT_MEMORY_DATA.value
    if memory_label in blocking:
        memory_detail = "Memory data is insufficient and required by profile."
        items.append(ChecklistItem("memory_data", CHECK_FAIL, memory_detail))
    elif memory_label in reducers:
        items.append(
            ChecklistItem(
                "memory_data",
                CHECK_WARNING,
                "Memory data is insufficient; treated as a confidence reducer.",
            )
        )
    else:
        items.append(
            ChecklistItem("memory_data", CHECK_PASS, "Memory data is sufficient.")
        )

    # ----- Option availability row ---------------------------------------
    if sufficiency.option_status == SUFFICIENCY_OPTION_OK:
        items.append(
            ChecklistItem(
                "option_data_available",
                CHECK_PASS,
                "Option data is available and usable.",
            )
        )
    elif sufficiency.option_status == SUFFICIENCY_OPTION_NOT_AVAILABLE:
        items.append(
            ChecklistItem(
                "option_data_available",
                CHECK_WARNING,
                "No option data supplied; stock-only analysis is unaffected.",
            )
        )
    else:
        # INSUFFICIENT_OPTION_DATA
        items.append(
            ChecklistItem(
                "option_data_available",
                CHECK_WARNING,
                "Option data supplied but unusable; blocks option suitability only.",
            )
        )

    # ----- Hard filter outcomes (each filter is its own row) -------------
    for outcome in hard_filter.outcomes:
        items.append(
            ChecklistItem(
                name=f"hard_filter.{outcome.name}",
                status=_status_for_outcome(outcome.status),
                detail=outcome.detail or "",
            )
        )

    # ----- Event risk -----------------------------------------------------
    items.append(
        ChecklistItem(
            name="event_risk_level",
            status=_status_for_risk(event_risk.risk_level),
            detail=(
                f"Event risk = {event_risk.risk_level}: "
                + ("; ".join(event_risk.factors) if event_risk.factors else "no factors")
            ),
        )
    )

    # ----- Memory risk ----------------------------------------------------
    items.append(
        ChecklistItem(
            name="memory_risk_level",
            status=_status_for_risk(memory_risk.risk_level),
            detail=(
                f"Memory risk = {memory_risk.risk_level}: "
                + ("; ".join(memory_risk.factors) if memory_risk.factors else "no factors")
            ),
        )
    )

    return items


def _item(
    name: str,
    is_pass: bool,
    fail_status: str,
    *,
    pass_detail: str,
    fail_detail: str,
) -> ChecklistItem:
    return ChecklistItem(
        name=name,
        status=CHECK_PASS if is_pass else fail_status,
        detail=pass_detail if is_pass else fail_detail,
    )


def _three_state_status(
    label: str,
    blocking: set[str],
    non_blocking: set[str],
    *,
    pass_detail: str,
    warn_detail: str,
    fail_detail: str,
) -> tuple[str, str]:
    if label in blocking:
        return CHECK_FAIL, fail_detail
    if label in non_blocking:
        return CHECK_WARNING, warn_detail
    return CHECK_PASS, pass_detail


def _status_for_outcome(status: str) -> str:
    if status == FAIL:
        return CHECK_FAIL
    if status == WARN:
        return CHECK_WARNING
    if status == PASS:
        return CHECK_PASS
    if status == SKIPPED:
        return CHECK_SKIPPED
    return CHECK_SKIPPED


def _status_for_risk(risk_level: str) -> str:
    if risk_level == RISK_HIGH:
        return CHECK_FAIL
    if risk_level == RISK_MEDIUM:
        return CHECK_WARNING
    if risk_level == RISK_UNKNOWN:
        return CHECK_SKIPPED
    return CHECK_PASS


__all__ = ["ChecklistItem", "build_opportunity_checklist"]
