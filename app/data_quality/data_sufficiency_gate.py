"""Phase 19 — Data Sufficiency Gate.

A thin, additive coordination layer that consumes the existing Phase 6 /
Phase 12 / Phase 14 / Phase 15 outputs already in the database and decides:

* whether stock-only analysis is **allowed or blocked** for a symbol,
* whether option suitability has enough data to run at all,
* which insufficiencies are **non-blocking warnings or confidence reducers**.

The gate never recomputes price or setup math itself, never invents option
values, and never persists anything. It returns a ``GateDecision`` and a
list of practical "what data to add" actions produced by
``insufficient_data_action_builder``.

Phase 19 rule (verbatim from the outline):

* ``INSUFFICIENT_PRICE_HISTORY``       — blocking for stock decision
* ``INSUFFICIENT_STOCK_SETUP_DATA``    — blocking for stock decision
* ``OPTION_DATA_NOT_AVAILABLE``        — non-blocking for stock-only decision
* ``INSUFFICIENT_OPTION_DATA``         — blocks option suitability only

News / IV / earnings / memory insufficiency are warnings or confidence
reducers by default, and are promoted to stock blockers only when the
active strategy profile flags them as required (Phase 19 profile flags
``requires_news_data``, ``requires_iv_history``, ``requires_earnings_data``,
``requires_memory_data``; all default to ``False``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.data_quality.data_quality_checker import (
    DataQualityChecker,
    DataQualityResult,
)
from app.data_quality.data_sufficiency_labels import (
    DataSufficiencyLabel,
)
from app.data_quality.insufficient_data_action_builder import (
    InsufficientDataActionBuilder,
)
from app.database.models import Event
from app.earnings.earnings_models import EarningsEvent
from app.iv_history.iv_models import IvHistoryDay
from app.profiles.profile_manager import profile_manager
from app.profiles.profile_models import StrategyProfile
from app.quant.stock_setup_models import StockSetup

# --- Phase 19 gate-level status strings -------------------------------------

STOCK_DECISION_ALLOWED = "STOCK_DECISION_ALLOWED"
STOCK_DECISION_BLOCKED = "STOCK_DECISION_BLOCKED"

OPTION_OK = "OPTION_OK"
OPTION_DATA_NOT_AVAILABLE = DataSufficiencyLabel.OPTION_DATA_NOT_AVAILABLE.value
INSUFFICIENT_OPTION_DATA = DataSufficiencyLabel.INSUFFICIENT_OPTION_DATA.value
OPTION_ANALYSIS_NOT_REQUESTED = "OPTION_ANALYSIS_NOT_REQUESTED"

# Minimum daily price rows required before a stock decision can be made.
# Aligned with ``app.quant.support_resistance.MINIMUM_PRICE_ROWS_FOR_SWINGS``
# (which is the threshold the Phase 12 setup service already uses to emit
# ``INSUFFICIENT_PRICE_HISTORY``). Kept here as a separate constant so the
# gate can be unit-tested with arbitrary row counts.
DEFAULT_MIN_PRICE_ROWS = 50

# Minimum row count before the gate considers memory data "sufficient".
DEFAULT_MIN_MEMORY_ROWS = 1


# --- Result dataclasses -----------------------------------------------------


@dataclass(frozen=True)
class GateDecision:
    """Phase 19 verdict for a single symbol.

    The shape is intentionally simple and stable so future phases
    (decision intelligence, hard filters, dashboard) can read it without
    coupling to internal data-quality details.
    """

    symbol: str | None
    stock_decision_status: str
    option_status: str

    blocking_labels: list[str] = field(default_factory=list)
    non_blocking_labels: list[str] = field(default_factory=list)
    confidence_reducers: list[str] = field(default_factory=list)

    reasons: list[str] = field(default_factory=list)
    actions: list[dict[str, Any]] = field(default_factory=list)

    profile_name: str | None = None
    profile_version: str | None = None

    evaluated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "stock_decision_status": self.stock_decision_status,
            "option_status": self.option_status,
            "blocking_labels": list(self.blocking_labels),
            "non_blocking_labels": list(self.non_blocking_labels),
            "confidence_reducers": list(self.confidence_reducers),
            "reasons": list(self.reasons),
            "actions": list(self.actions),
            "profile_name": self.profile_name,
            "profile_version": self.profile_version,
            "evaluated_at": self.evaluated_at.isoformat(),
        }


@dataclass(frozen=True)
class SufficiencyInputs:
    """Pre-computed inputs for the gate.

    Used by unit tests that want to drive the gate without a database. The
    DB-facing entry point ``evaluate_symbol`` builds one of these from the
    existing tables before calling ``evaluate_inputs``.
    """

    symbol: str | None = None
    price_rows: list[dict[str, Any]] | None = None
    stock_setup_status: str | None = None
    stock_setup_reasons: list[str] = field(default_factory=list)
    option_rows: list[dict[str, Any]] | None = None
    option_data_requested: bool = False
    news_rows: list[dict[str, Any]] | None = None
    iv_history_rows: list[dict[str, Any]] | None = None
    earnings_rows: list[dict[str, Any]] | None = None
    memory_rows: list[dict[str, Any]] | None = None


# --- The gate ---------------------------------------------------------------


class DataSufficiencyGate:
    """Coordinates per-category sufficiency checks into a single decision.

    Reuses ``DataQualityChecker`` for the per-category math. Adds the Phase 19
    classification on top: which labels are blocking for stock, which are
    blocking for option suitability only, and which are warnings.
    """

    def __init__(
        self,
        checker: DataQualityChecker | None = None,
        action_builder: InsufficientDataActionBuilder | None = None,
        min_price_rows: int = DEFAULT_MIN_PRICE_ROWS,
        min_memory_rows: int = DEFAULT_MIN_MEMORY_ROWS,
    ) -> None:
        self.checker = checker or DataQualityChecker()
        self.action_builder = action_builder or InsufficientDataActionBuilder()
        self.min_price_rows = min_price_rows
        self.min_memory_rows = min_memory_rows

    # ------------------------------------------------------------------ DB path

    def evaluate_symbol(
        self,
        db: Session,
        symbol: str,
        *,
        option_data_requested: bool = False,
        profile: StrategyProfile | None = None,
    ) -> GateDecision:
        """Build ``SufficiencyInputs`` from the existing tables and evaluate.

        This is non-destructive: only reads are performed. No row is created
        and no row is updated. Tables are created lazily by the underlying
        services elsewhere; the gate does not call ``create_all`` so unit
        tests can drive it against either SQLite or the real Postgres.
        """

        clean_symbol = (symbol or "").strip().upper() or None
        inputs = self._build_inputs(
            db=db,
            symbol=clean_symbol,
            option_data_requested=option_data_requested,
        )
        return self.evaluate_inputs(inputs=inputs, profile=profile)

    # ----------------------------------------------------------------- pure path

    def evaluate_inputs(
        self,
        inputs: SufficiencyInputs,
        *,
        profile: StrategyProfile | None = None,
    ) -> GateDecision:
        """Apply the Phase 19 classification to pre-computed inputs."""

        active_profile = profile or self._safe_active_profile()

        blocking: list[str] = []
        non_blocking: list[str] = []
        confidence_reducers: list[str] = []
        reasons: list[str] = []

        # Step 19.2 -- price history (blocking).
        price_result = self.checker.check_price_history(
            price_rows=inputs.price_rows,
            symbol=inputs.symbol,
            min_required_rows=self.min_price_rows,
        )
        if price_result.label != DataSufficiencyLabel.SUFFICIENT:
            blocking.append(DataSufficiencyLabel.INSUFFICIENT_PRICE_HISTORY.value)
            reasons.append(price_result.reason)

        # Step 19.3 -- stock setup sufficiency (blocking).
        #
        # The Phase 12/14 service emits the legacy ``INSUFFICIENT_SETUP_DATA``
        # string and ``INSUFFICIENT_PRICE_HISTORY``. The gate normalizes the
        # legacy spelling to the Phase 19 canonical ``INSUFFICIENT_STOCK_SETUP_DATA``
        # for its public output, while existing stored rows and existing tests
        # keep using the legacy string.
        setup_label = self._normalize_setup_status(inputs.stock_setup_status)
        if setup_label is not None:
            if setup_label == DataSufficiencyLabel.INSUFFICIENT_PRICE_HISTORY.value:
                # Already added above via the price check; avoid double-counting.
                if setup_label not in blocking:
                    blocking.append(setup_label)
            else:
                if setup_label not in blocking:
                    blocking.append(setup_label)
            if inputs.stock_setup_reasons:
                reasons.extend(inputs.stock_setup_reasons)
            else:
                reasons.append(
                    f"Stock setup is not ready: {setup_label}."
                )

        # Step 19.4 -- option data availability (non-blocking for stock-only).
        option_status = self._classify_option_status(
            option_rows=inputs.option_rows,
            option_data_requested=inputs.option_data_requested,
            symbol=inputs.symbol,
            non_blocking=non_blocking,
            reasons=reasons,
        )

        # Step 19.5 -- news sufficiency (warning unless required).
        news_result = self.checker.check_news_data(
            news_rows=inputs.news_rows,
            symbol=inputs.symbol,
        )
        if news_result.label != DataSufficiencyLabel.SUFFICIENT:
            news_label = DataSufficiencyLabel.INSUFFICIENT_NEWS_DATA.value
            if self._profile_requires(active_profile, "requires_news_data"):
                blocking.append(news_label)
                reasons.append(
                    f"{news_result.reason} Profile requires news data."
                )
            else:
                non_blocking.append(news_label)
                reasons.append(news_result.reason)

        # Step 19.6 -- IV sufficiency (optional warning).
        iv_label = self._evaluate_iv_history(inputs.iv_history_rows, inputs.symbol)
        if iv_label is not None:
            label_value, label_reason = iv_label
            if self._profile_requires(active_profile, "requires_iv_history"):
                blocking.append(label_value)
                reasons.append(f"{label_reason} Profile requires IV history.")
            else:
                non_blocking.append(label_value)
                reasons.append(label_reason)

        # Step 19.7 -- earnings sufficiency (warning / risk context).
        earnings_label = self._evaluate_earnings(
            inputs.earnings_rows, inputs.symbol
        )
        if earnings_label is not None:
            label_value, label_reason = earnings_label
            if self._profile_requires(active_profile, "requires_earnings_data"):
                blocking.append(label_value)
                reasons.append(
                    f"{label_reason} Profile requires earnings data."
                )
            else:
                non_blocking.append(label_value)
                reasons.append(label_reason)

        # Step 19.8 -- memory sufficiency (confidence reducer, never hard block
        # unless the profile asks for it).
        memory_result = self.checker.check_memory_data(
            memory_rows=inputs.memory_rows,
            symbol=inputs.symbol,
            min_required_rows=self.min_memory_rows,
        )
        if memory_result.label != DataSufficiencyLabel.SUFFICIENT:
            memory_label = DataSufficiencyLabel.INSUFFICIENT_MEMORY_DATA.value
            if self._profile_requires(active_profile, "requires_memory_data"):
                blocking.append(memory_label)
                reasons.append(
                    f"{memory_result.reason} Profile requires memory data."
                )
            else:
                # Confidence reducer by default — not a non-blocking *warning*
                # and not a hard block. Phase 19 outline treats memory as its
                # own bucket so downstream phases can deflate confidence
                # without showing the user a hard warning.
                confidence_reducers.append(memory_label)
                reasons.append(memory_result.reason)

        # Step 19.9 -- output blocking vs non-blocking labels.
        stock_decision_status = (
            STOCK_DECISION_BLOCKED if blocking else STOCK_DECISION_ALLOWED
        )

        # Step 19.10 -- suggest practical next steps via the action builder.
        actions = self.action_builder.build_actions(
            blocking_labels=blocking,
            non_blocking_labels=non_blocking,
            confidence_reducers=confidence_reducers,
            option_status=option_status,
            symbol=inputs.symbol,
        )

        return GateDecision(
            symbol=inputs.symbol,
            stock_decision_status=stock_decision_status,
            option_status=option_status,
            blocking_labels=_dedupe(blocking),
            non_blocking_labels=_dedupe(non_blocking),
            confidence_reducers=_dedupe(confidence_reducers),
            reasons=reasons,
            actions=actions,
            profile_name=active_profile.profile_name if active_profile else None,
            profile_version=active_profile.profile_version if active_profile else None,
        )

    # ------------------------------------------------------------ DB helpers

    def _build_inputs(
        self,
        db: Session,
        symbol: str | None,
        option_data_requested: bool,
    ) -> SufficiencyInputs:
        if symbol is None:
            return SufficiencyInputs(
                symbol=None,
                price_rows=[],
                stock_setup_status=None,
                option_rows=None,
                option_data_requested=option_data_requested,
                news_rows=[],
                iv_history_rows=[],
                earnings_rows=[],
                memory_rows=[],
            )

        price_rows = self._load_price_rows(db, symbol)
        setup_status, setup_reasons = self._load_stock_setup_status(db, symbol)
        news_rows = self._load_news_rows(db, symbol)
        iv_rows = self._load_iv_history_rows(db, symbol)
        earnings_rows = self._load_earnings_rows(db, symbol)

        # Option data: the gate intentionally does *not* materialize an option
        # chain itself. Manual option snapshots are pasted through Phase 8/15.
        # Until manual snapshot rows are loaded for a symbol, the gate treats
        # option data as "not available" (non-blocking) -- which is exactly
        # the Phase 15 behaviour the existing tests already protect.
        option_rows = self._load_manual_option_rows(db, symbol)

        return SufficiencyInputs(
            symbol=symbol,
            price_rows=price_rows,
            stock_setup_status=setup_status,
            stock_setup_reasons=setup_reasons,
            option_rows=option_rows,
            option_data_requested=option_data_requested,
            news_rows=news_rows,
            iv_history_rows=iv_rows,
            earnings_rows=earnings_rows,
            memory_rows=[],  # Phase 19 does not yet have a memory store.
        )

    def _load_price_rows(self, db: Session, symbol: str) -> list[dict[str, Any]]:
        # Imported here to keep ``data_quality`` import-free at module load
        # time for the pure-input test path.
        from app.database.models import DailyPrice

        try:
            rows = (
                db.query(DailyPrice)
                .filter(DailyPrice.symbol == symbol)
                .order_by(DailyPrice.price_date.asc())
                .all()
            )
        except SQLAlchemyError:
            # Defensive: the underlying table may not be materialised yet
            # (Phase 19 evaluates eagerly before downstream services have
            # ``ensure_tables`` run). Fall back to "no data available".
            return []

        return [
            {
                "date": r.price_date,
                "open": r.open_price,
                "high": r.high_price,
                "low": r.low_price,
                "close": r.close_price,
                "volume": r.volume,
            }
            for r in rows
        ]

    def _load_stock_setup_status(
        self, db: Session, symbol: str
    ) -> tuple[str | None, list[str]]:
        try:
            row: StockSetup | None = (
                db.query(StockSetup)
                .filter(StockSetup.symbol == symbol)
                .order_by(StockSetup.snapshot_date.desc(), StockSetup.id.desc())
                .first()
            )
        except SQLAlchemyError:
            return None, []
        if row is None:
            return None, []
        return row.data_sufficiency_status, list(row.insufficient_reasons_json or [])

    def _load_news_rows(self, db: Session, symbol: str) -> list[dict[str, Any]]:
        try:
            rows = (
                db.query(Event)
                .filter(Event.symbol == symbol)
                .order_by(Event.event_time.desc().nullslast())
                .limit(50)
                .all()
            )
        except SQLAlchemyError:
            # Defensive: the underlying table may not be materialised yet
            # (Phase 19 evaluates eagerly before downstream services have
            # ``ensure_tables`` run). Fall back to "no data available".
            return []
        return [
            {
                "source": r.source,
                "title": r.headline,
                "event_time": r.event_time,
            }
            for r in rows
        ]

    def _load_iv_history_rows(
        self, db: Session, symbol: str
    ) -> list[dict[str, Any]]:
        try:
            rows = (
                db.query(IvHistoryDay)
                .filter(IvHistoryDay.symbol == symbol)
                .order_by(IvHistoryDay.snapshot_date.desc())
                .limit(120)
                .all()
            )
        except SQLAlchemyError:
            # Defensive: the underlying table may not be materialised yet
            # (Phase 19 evaluates eagerly before downstream services have
            # ``ensure_tables`` run). Fall back to "no data available".
            return []
        return [
            {"snapshot_date": r.snapshot_date, "atm_iv_30d": r.atm_iv_30d}
            for r in rows
        ]

    def _load_earnings_rows(
        self, db: Session, symbol: str
    ) -> list[dict[str, Any]]:
        try:
            rows = (
                db.query(EarningsEvent)
                .filter(EarningsEvent.symbol == symbol)
                .order_by(EarningsEvent.earnings_datetime_utc.desc())
                .limit(20)
                .all()
            )
        except SQLAlchemyError:
            # Defensive: the underlying table may not be materialised yet
            # (Phase 19 evaluates eagerly before downstream services have
            # ``ensure_tables`` run). Fall back to "no data available".
            return []
        return [
            {
                "symbol": r.symbol,
                "earnings_datetime_utc": r.earnings_datetime_utc,
                "source": r.source,
            }
            for r in rows
        ]

    def _load_manual_option_rows(
        self, db: Session, symbol: str
    ) -> list[dict[str, Any]] | None:
        # The Phase 8/15 manual option service stores snapshots via raw SQL in a
        # ``manual_option_snapshots`` table. Phase 19 does not require option
        # data to make a stock decision, so the gate does not introspect that
        # table here -- callers that have a known option snapshot can pass
        # rows through ``evaluate_inputs`` directly. Returning ``None`` here
        # is the canonical "no option data was supplied to the gate" signal,
        # which yields ``OPTION_DATA_NOT_AVAILABLE`` (non-blocking).
        return None

    # ------------------------------------------------------------ classifiers

    def _normalize_setup_status(self, raw_status: str | None) -> str | None:
        """Return the gate-level label for a stored setup status, or None.

        Legacy ``INSUFFICIENT_SETUP_DATA`` is mapped to the Phase 19 spelling
        ``INSUFFICIENT_STOCK_SETUP_DATA``. ``INSUFFICIENT_PRICE_HISTORY`` is
        passed through. Anything else (SUFFICIENT, PARTIAL, UNKNOWN, None) is
        not a stock-setup block.
        """
        if not raw_status:
            return None
        status = raw_status.strip().upper()
        if status in {"SUFFICIENT", "PARTIAL", "UNKNOWN", ""}:
            return None
        if status == DataSufficiencyLabel.INSUFFICIENT_SETUP_DATA.value:
            return DataSufficiencyLabel.INSUFFICIENT_STOCK_SETUP_DATA.value
        if status == DataSufficiencyLabel.INSUFFICIENT_STOCK_SETUP_DATA.value:
            return status
        if status == DataSufficiencyLabel.INSUFFICIENT_PRICE_HISTORY.value:
            return status
        return None

    def _classify_option_status(
        self,
        option_rows: list[dict[str, Any]] | None,
        option_data_requested: bool,
        symbol: str | None,
        non_blocking: list[str],
        reasons: list[str],
    ) -> str:
        """Phase 19 step 19.4.

        * ``option_rows is None`` or empty -> OPTION_DATA_NOT_AVAILABLE
          (non-blocking for stock-only decisions, always).
        * Rows present but checker flags them as INSUFFICIENT_OPTION_DATA ->
          INSUFFICIENT_OPTION_DATA (blocks option suitability only -- never
          added to the gate's stock-blocking list).
        * Rows present and SUFFICIENT -> OPTION_OK.

        ``option_data_requested`` controls the reason text but never promotes
        a missing chain to a stock-blocking state. Phase 15's
        ``MANUAL_OPTION_INPUT_NEEDED`` remains the suitability-engine signal
        for "an option was requested but none was supplied"; the gate stays
        agnostic and only reports availability.
        """
        if not option_rows:
            if option_data_requested:
                reasons.append(
                    "Option analysis was requested but no option data is "
                    "available; stock-only analysis is unaffected."
                )
            else:
                reasons.append(
                    "No option data supplied; stock-only analysis is unaffected."
                )
            # Surface availability as a non-blocking label so dashboards can
            # render the state cleanly.
            non_blocking.append(OPTION_DATA_NOT_AVAILABLE)
            return OPTION_DATA_NOT_AVAILABLE

        option_result: DataQualityResult = self.checker.check_option_data(
            option_rows=option_rows,
            symbol=symbol,
        )
        if option_result.label == DataSufficiencyLabel.SUFFICIENT:
            return OPTION_OK

        # INSUFFICIENT_OPTION_DATA -- option exists but is unusable. The
        # Phase 19 rule says this blocks option suitability only. We do *not*
        # add it to ``blocking`` (stock list); we surface it on the option
        # status field and as a non-blocking label so the gate decision is
        # self-describing.
        non_blocking.append(INSUFFICIENT_OPTION_DATA)
        reasons.append(option_result.reason)
        return INSUFFICIENT_OPTION_DATA

    def _evaluate_iv_history(
        self,
        iv_history_rows: list[dict[str, Any]] | None,
        symbol: str | None,
    ) -> tuple[str, str] | None:
        rows = iv_history_rows or []
        if not rows:
            return (
                DataSufficiencyLabel.INSUFFICIENT_IV_DATA.value,
                "No IV history rows are available; IV risk context is limited.",
            )
        # Defer to the existing checker; surface its WARNING under the
        # Phase 19 canonical label ``INSUFFICIENT_IV_DATA``.
        result = self.checker.check_iv_history_data(
            iv_history_rows=rows, symbol=symbol, minimum_rows=30
        )
        if result.label == DataSufficiencyLabel.SUFFICIENT:
            return None
        return (
            DataSufficiencyLabel.INSUFFICIENT_IV_DATA.value,
            result.reason,
        )

    def _evaluate_earnings(
        self,
        earnings_rows: list[dict[str, Any]] | None,
        symbol: str | None,
    ) -> tuple[str, str] | None:
        rows = earnings_rows or []
        if not rows:
            return (
                DataSufficiencyLabel.INSUFFICIENT_EARNINGS_DATA.value,
                "No earnings calendar rows are available for this symbol.",
            )
        return None

    # ------------------------------------------------------------ profile glue

    @staticmethod
    def _profile_requires(profile: StrategyProfile | None, attr: str) -> bool:
        if profile is None:
            return False
        return bool(getattr(profile, attr, False))

    @staticmethod
    def _safe_active_profile() -> StrategyProfile | None:
        try:
            return profile_manager.get_active_profile()
        except Exception:
            return None


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for v in values:
        if v in seen:
            continue
        seen.add(v)
        out.append(v)
    return out


# Importing ``date`` for type completeness; the dataclasses use ``datetime``
# but the SQL helpers above accept either.
__all__ = [
    "DataSufficiencyGate",
    "GateDecision",
    "INSUFFICIENT_OPTION_DATA",
    "OPTION_ANALYSIS_NOT_REQUESTED",
    "OPTION_DATA_NOT_AVAILABLE",
    "OPTION_OK",
    "STOCK_DECISION_ALLOWED",
    "STOCK_DECISION_BLOCKED",
    "SufficiencyInputs",
    "date",
]
