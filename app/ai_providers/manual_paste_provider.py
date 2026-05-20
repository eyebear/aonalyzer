"""Manual paste / free web AI providers (Phase 17, step 17.7).

These do not call any API. They render the prompt for the user to paste into an
external AI tool (a paid chat UI or a free web AI), and the user pastes the
answer back into the app. ``generate`` returns ``MANUAL_REQUIRED`` with the
rendered prompt -- a first-class non-blocking state, not an error.
"""

from __future__ import annotations

from app.ai_providers.provider_base import AIProvider, AIRequest, AIResponse
from app.ai_providers.provider_types import FREE_WEB_AI, MANUAL_PASTE, MANUAL_REQUIRED


class ManualPasteProvider(AIProvider):
    provider_type = MANUAL_PASTE
    _reason = "Copy this prompt into your AI tool, then paste the answer back into the app."

    def is_available(self) -> bool:
        # The manual workflow is always usable (it needs no network/keys).
        return True

    def generate(self, request: AIRequest) -> AIResponse:
        return AIResponse(
            status=MANUAL_REQUIRED,
            provider_type=self.provider_type,
            task_type=request.task_type,
            text=None,
            manual_prompt=request.rendered_prompt(),
            fallback_reason=self._reason,
        )


class FreeWebAiProvider(ManualPasteProvider):
    provider_type = FREE_WEB_AI
    _reason = (
        "Paste this prompt into a free web AI (e.g. a browser chat), "
        "then paste the answer back into the app."
    )


__all__ = ["FreeWebAiProvider", "ManualPasteProvider"]
