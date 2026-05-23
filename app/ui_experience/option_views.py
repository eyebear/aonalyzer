"""Phase 34 — Manual Option Review display helpers (pure, testable).

Transforms a manual option snapshot (+ optional suitability candidate) into the
row the Manual Option Review page renders. DTE / premium / liquidity / IV /
Greeks / breakeven are shown only when available or calculable; missing fields
are surfaced honestly and never invented. Never implies a live broker
option-chain feed.
"""

from __future__ import annotations

from typing import Any

MANUAL_OPTION_EMPTY_STATE = (
    "No manual option data is available. You can paste option information from "
    "a chosen website or broker to evaluate option contracts. Stock-only "
    "analysis can still continue without any option data."
)


def _premium(snapshot: dict[str, Any]) -> float | None:
    """Premium = last price if present, else mid price (both may be absent)."""
    last = snapshot.get("last_price")
    if last is not None:
        return last
    return snapshot.get("mid_price")


def build_manual_option_review_row(
    snapshot: dict[str, Any],
    candidate: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """One Manual Option Review row. Only present values are shown."""
    premium = _premium(snapshot)
    suitability_status = None
    rejection_reasons: list[str] = []
    if candidate is not None:
        suitability_status = candidate.get("suitability_label") or candidate.get(
            "status"
        )
        rejection_reasons = candidate.get("rejection_reasons", []) or candidate.get(
            "failed_checks", []
        )

    return {
        "id": snapshot.get("id"),
        "symbol": snapshot.get("symbol"),
        "option_type": snapshot.get("option_type"),
        "expiration_date": snapshot.get("expiration_date"),
        "dte": snapshot.get("dte"),
        "strike": snapshot.get("strike"),
        "premium": premium,
        "contract_cost": snapshot.get("contract_cost"),
        # Liquidity (shown only when available).
        "bid": snapshot.get("bid"),
        "ask": snapshot.get("ask"),
        "spread_percent": snapshot.get("spread_percent"),
        "open_interest": snapshot.get("open_interest"),
        "volume": snapshot.get("volume"),
        # IV / Greeks (shown only when available).
        "implied_volatility": snapshot.get("implied_volatility"),
        "delta": snapshot.get("delta"),
        "gamma": snapshot.get("gamma"),
        "theta": snapshot.get("theta"),
        "vega": snapshot.get("vega"),
        # Contract reality.
        "breakeven": snapshot.get("breakeven"),
        "breakeven_distance_percent": snapshot.get("breakeven_distance_percent"),
        # Data quality.
        "parser_confidence": snapshot.get("parser_confidence"),
        "missing_fields": snapshot.get("missing_fields", []),
        "data_quality_status": snapshot.get("data_quality_status"),
        "ai_summary": snapshot.get("ai_summary"),
        # Suitability outcome (only if a candidate was evaluated).
        "suitability_status": suitability_status,
        "rejection_reasons": rejection_reasons,
    }


def target_vs_breakeven(
    *, target_price: float | None, breakeven: float | None
) -> dict[str, Any]:
    """Phase 34.10 — the core option suitability check, only when calculable."""
    if target_price is None or breakeven is None:
        return {
            "calculable": False,
            "detail": "Target-vs-breakeven not calculable (target or breakeven missing).",
        }
    margin = target_price - breakeven
    return {
        "calculable": True,
        "target_price": target_price,
        "breakeven": breakeven,
        "margin": margin,
        "target_above_breakeven": margin > 0,
    }


__all__ = [
    "MANUAL_OPTION_EMPTY_STATE",
    "build_manual_option_review_row",
    "target_vs_breakeven",
]
