"""Phase 37, step 37.1 — AI Research Chat service.

Orchestrates: build deterministic context -> route answer mode -> assemble a
guard-railed system prompt -> call the AI provider -> assemble sources +
citations. When no provider is configured (or it declines), the service
returns a deterministic degraded-state answer built from the context instead
of failing.

Hard invariants enforced here (independent of any AI provider):

* The chat uses only the provided context.
* It NEVER invents missing option values; when option data is missing it says
  so, and when incomplete it explains what cannot be calculated.
* It NEVER overrides the deterministic decision / hard filters; answer modes
  shape the output format only.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.ai_providers.provider_manager import AIProviderManager
from app.ai_providers.provider_types import (
    OK,
    TASK_OPTION_TEXT_READER,
    TASK_RESEARCH_CHAT,
)
from app.chat.answer_modes import (
    MODE_ACTION_PLAN,
    MODE_COUNTERARGUMENT,
    MODE_DECISION_TRACE,
    MODE_OPTION_TEXT_READER,
    MODE_RISK_REVIEW,
    MODE_SIMILAR_CASE,
    mode_instruction,
    route_mode,
)
from app.chat.citation_builder import build_citations, retrieve_sources
from app.chat.context_builder import (
    OPTION_DATA_INCOMPLETE,
    OPTION_DATA_NOT_AVAILABLE,
    ChatContext,
    ChatContextBuilder,
)

SYSTEM_GUARDRAILS = (
    "You are aonalyzer's research assistant. Use ONLY the provided JSON context. "
    "Do not use outside knowledge or invent any values. If option data is "
    "missing, say it is missing. If option data is incomplete, explain exactly "
    "what cannot be calculated and never fabricate bid/ask/strike/IV/Greeks. "
    "Never override the system's deterministic decision or hard filters; you "
    "explain and reformat, you do not change the verdict. This is research and "
    "decision support, not financial advice and not auto-trading."
)


@dataclass
class ChatResponse:
    symbol: str | None
    mode: str
    question: str
    answer: str
    degraded: bool
    provider_status: str
    provider_type: str | None
    option_data_status: str
    sources: list[dict[str, Any]] = field(default_factory=list)
    citations: list[dict[str, Any]] = field(default_factory=list)
    context_summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "mode": self.mode,
            "question": self.question,
            "answer": self.answer,
            "degraded": self.degraded,
            "provider_status": self.provider_status,
            "provider_type": self.provider_type,
            "option_data_status": self.option_data_status,
            "sources": list(self.sources),
            "citations": list(self.citations),
            "context_summary": dict(self.context_summary),
        }


class ChatService:
    def __init__(
        self,
        context_builder: ChatContextBuilder | None = None,
        provider_manager: AIProviderManager | None = None,
    ) -> None:
        self.context_builder = context_builder or ChatContextBuilder()
        # A real manager defaults to DISABLED unless configured, so a missing
        # provider yields a deterministic degraded answer rather than an error.
        self.provider_manager = provider_manager or AIProviderManager()

    def answer(
        self,
        db: Session,
        *,
        question: str,
        symbol: str | None = None,
        mode: str | None = None,
        manual_option_snapshot_id: int | None = None,
        option_data_requested: bool = False,
    ) -> ChatResponse:
        resolved_mode = route_mode(mode)
        context = self.context_builder.build(
            db,
            symbol or "",
            manual_option_snapshot_id=manual_option_snapshot_id,
            option_data_requested=option_data_requested,
        )

        system_prompt = self._system_prompt(resolved_mode, context)
        user_prompt = (question or "").strip() or mode_instruction(resolved_mode)

        task = (
            TASK_OPTION_TEXT_READER
            if resolved_mode == MODE_OPTION_TEXT_READER
            else TASK_RESEARCH_CHAT
        )
        ai_response = self.provider_manager.generate(
            task,
            user_prompt,
            system_prompt=system_prompt,
            metadata={"mode": resolved_mode, "symbol": context.symbol},
        )

        degraded = ai_response.status != OK or not (ai_response.text or "").strip()
        if degraded:
            answer = self._degraded_answer(resolved_mode, context, question)
        else:
            answer = ai_response.text or ""

        return ChatResponse(
            symbol=context.symbol,
            mode=resolved_mode,
            question=question,
            answer=answer,
            degraded=degraded,
            provider_status=ai_response.status,
            provider_type=ai_response.provider_type,
            option_data_status=context.option_data_status,
            sources=retrieve_sources(context),
            citations=build_citations(context),
            context_summary=self._context_summary(context),
        )

    # --------------------------------------------------------- prompt assembly

    def _system_prompt(self, mode: str, context: ChatContext) -> str:
        return (
            f"{SYSTEM_GUARDRAILS}\n\n"
            f"ANSWER MODE: {mode}. {mode_instruction(mode)}\n\n"
            f"CONTEXT (JSON, the only ground truth):\n"
            f"{json.dumps(context.to_dict(), default=str)}"
        )

    def _context_summary(self, context: ChatContext) -> dict[str, Any]:
        return {
            "symbol": context.symbol,
            "final_action_label": context.final_action_label,
            "option_data_status": context.option_data_status,
            "has_manual_snapshot": context.has_manual_snapshot,
            "missing_option_fields": context.missing_option_fields,
            "events": len(context.events),
            "similar_cases": len(context.similar_cases),
        }

    # ------------------------------------------------------ degraded answers

    def _option_status_sentence(self, context: ChatContext) -> str:
        if context.option_data_status == OPTION_DATA_NOT_AVAILABLE:
            return (
                "Option data is not available, so the option side was not "
                "evaluated; stock-only analysis still applies."
            )
        if context.option_data_status == OPTION_DATA_INCOMPLETE:
            missing = ", ".join(context.missing_option_fields) or "some fields"
            return (
                "Option data is incomplete: missing "
                f"{missing}. Option suitability cannot be fully calculated "
                "until those fields are provided; no values are invented."
            )
        return "Option data is available and was evaluated."

    def _degraded_answer(self, mode: str, context: ChatContext, question: str) -> str:
        symbol = context.symbol or "this symbol"
        label = context.final_action_label or "no decision yet"
        option_sentence = self._option_status_sentence(context)
        header = (
            "AI provider not configured — deterministic summary from the "
            "system context (no external model used).\n"
        )

        if mode == MODE_DECISION_TRACE:
            steps = context.decision_trace or []
            lines = [f"- {s.get('label', s)}" for s in steps] or ["- (no trace available)"]
            body = (
                f"Decision trace for {symbol} (verdict: {label}):\n"
                + "\n".join(lines)
                + f"\n{option_sentence}"
            )
        elif mode == MODE_ACTION_PLAN:
            body = (
                f"Action plan for {symbol}: the system verdict is {label}. "
                f"Follow the action items in the action suggestion. {option_sentence}"
            )
        elif mode == MODE_RISK_REVIEW:
            risks = []
            if context.earnings:
                risks.append(f"earnings risk: {context.earnings.get('risk_label')}")
            if context.iv:
                risks.append(f"IV risk: {context.iv.get('risk_label')}")
            if not risks:
                risks.append("no elevated event/IV/earnings risk recorded")
            body = (
                f"Risk review for {symbol} (verdict: {label}): "
                + "; ".join(risks)
                + f". {option_sentence}"
            )
        elif mode == MODE_COUNTERARGUMENT:
            body = (
                f"Counterargument to the {label} verdict for {symbol}: consider "
                "regime shifts, weak follow-through, or news not yet priced in. "
                f"This does not change the deterministic verdict. {option_sentence}"
            )
        elif mode == MODE_SIMILAR_CASE:
            if context.similar_cases:
                body = (
                    f"{len(context.similar_cases)} similar case(s) on file for "
                    f"{symbol}. {option_sentence}"
                )
            else:
                body = (
                    f"No similar historical cases are stored for {symbol} yet. "
                    f"{option_sentence}"
                )
        elif mode == MODE_OPTION_TEXT_READER:
            if context.manual_option is None:
                body = (
                    "No option text has been pasted for this symbol. Paste a "
                    "contract to have it read. No values are invented."
                )
            else:
                body = (
                    f"Pasted option for {symbol}: "
                    f"{json.dumps(context.manual_option, default=str)}. "
                    f"{option_sentence}"
                )
        else:  # MODE_EXPLAIN and default
            body = (
                f"The system's verdict for {symbol} is {label}. "
                f"{context.rationale or ''} {option_sentence}"
            )

        return header + body


__all__ = ["ChatResponse", "ChatService", "SYSTEM_GUARDRAILS"]
