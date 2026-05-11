from __future__ import annotations

from typing import Any

from app.options.manual_option_models import ManualOptionSnapshotRecord


class ManualOptionAiReader:
    """
    Placeholder AI reader for manually pasted option text.

    This class does not call an external AI provider yet.
    It returns a structured placeholder analysis so the API route,
    storage flow, and tests can pass before the real AI Provider Manager
    is connected in a later phase.
    """

    def analyze_snapshot(
        self,
        snapshot: ManualOptionSnapshotRecord,
    ) -> dict[str, Any]:
        missing_fields = snapshot.missing_fields or []

        if snapshot.data_quality_status == "OPTION_TEXT_PARSED":
            label = "OPTION_TEXT_PARSED_NEEDS_REVIEW"
        elif snapshot.data_quality_status == "OPTION_DATA_NOT_AVAILABLE":
            label = "OPTION_DATA_NOT_AVAILABLE"
        else:
            label = "INSUFFICIENT_OPTION_DATA"

        summary_parts = [
            "Manual option text was saved and parsed.",
            "This is a placeholder AI interpretation.",
        ]

        if snapshot.symbol:
            summary_parts.append(f"Ticker: {snapshot.symbol}.")

        if snapshot.option_type and snapshot.strike is not None:
            summary_parts.append(
                f"Detected contract type: {snapshot.option_type} "
                f"with strike {snapshot.strike}."
            )

        if snapshot.expiration_date is not None:
            summary_parts.append(
                f"Detected expiration date: {snapshot.expiration_date.isoformat()}."
            )

        if snapshot.mid_price is not None:
            summary_parts.append(
                f"Estimated mid price: {snapshot.mid_price}."
            )

        if snapshot.breakeven is not None:
            summary_parts.append(
                f"Estimated breakeven: {snapshot.breakeven}."
            )

        if missing_fields:
            summary_parts.append(
                "Some fields are missing and should be checked manually."
            )

        return {
            "plain_english_summary": " ".join(summary_parts),
            "liquidity_comment": self._build_liquidity_comment(snapshot),
            "greeks_comment": self._build_greeks_comment(snapshot),
            "time_decay_comment": self._build_time_decay_comment(snapshot),
            "iv_comment": self._build_iv_comment(snapshot),
            "breakeven_comment": self._build_breakeven_comment(snapshot),
            "data_quality_warning": self._build_data_quality_warning(snapshot),
            "missing_fields": missing_fields,
            "suggested_next_check": self._build_suggested_next_check(snapshot),
            "option_interpretation_label": label,
        }

    def _build_liquidity_comment(
        self,
        snapshot: ManualOptionSnapshotRecord,
    ) -> str:
        if snapshot.bid is None or snapshot.ask is None:
            return "Bid/ask data is missing, so liquidity cannot be judged."

        if snapshot.spread_percent is None:
            return "Bid/ask spread could not be calculated."

        return (
            "Bid/ask spread was calculated from the pasted data. "
            "Review spread percent before treating this contract as usable."
        )

    def _build_greeks_comment(
        self,
        snapshot: ManualOptionSnapshotRecord,
    ) -> str:
        available = []

        if snapshot.delta is not None:
            available.append("delta")
        if snapshot.gamma is not None:
            available.append("gamma")
        if snapshot.theta is not None:
            available.append("theta")
        if snapshot.vega is not None:
            available.append("vega")
        if snapshot.rho is not None:
            available.append("rho")

        if not available:
            return "No Greeks were detected in the pasted text."

        return (
            "Detected Greeks: "
            + ", ".join(available)
            + ". Review them before using this option expression."
        )

    def _build_time_decay_comment(
        self,
        snapshot: ManualOptionSnapshotRecord,
    ) -> str:
        if snapshot.theta is None:
            return "Theta is missing, so time decay cannot be interpreted."

        return (
            "Theta was detected. Negative theta usually means the option "
            "loses value as time passes, all else equal."
        )

    def _build_iv_comment(
        self,
        snapshot: ManualOptionSnapshotRecord,
    ) -> str:
        if snapshot.implied_volatility is None:
            return "Implied volatility is missing."

        return "Implied volatility was detected from the pasted text."

    def _build_breakeven_comment(
        self,
        snapshot: ManualOptionSnapshotRecord,
    ) -> str:
        if snapshot.breakeven is None:
            return (
                "Breakeven could not be calculated because required fields "
                "are missing."
            )

        return (
            f"Breakeven was calculated as {snapshot.breakeven}. "
            "Compare this with the stock target before judging the option."
        )

    def _build_data_quality_warning(
        self,
        snapshot: ManualOptionSnapshotRecord,
    ) -> str:
        if snapshot.data_quality_status == "OPTION_TEXT_PARSED":
            return "Enough fields were detected for a basic option calculation."

        if snapshot.data_quality_status == "OPTION_DATA_NOT_AVAILABLE":
            return "No usable option data was detected."

        return "Option data is incomplete. Missing fields are listed separately."

    def _build_suggested_next_check(
        self,
        snapshot: ManualOptionSnapshotRecord,
    ) -> str:
        if snapshot.data_quality_status == "OPTION_TEXT_PARSED":
            return (
                "Review the parsed fields and compare breakeven against "
                "the stock target."
            )

        return (
            "Paste bid, ask, expiration, call/put, strike, volume, open interest, "
            "IV, and Greeks if available."
        )