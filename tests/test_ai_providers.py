from app.ai_providers.gemini_provider import GeminiProvider
from app.ai_providers.manual_paste_provider import FreeWebAiProvider, ManualPasteProvider
from app.ai_providers.ollama_provider import OllamaProvider
from app.ai_providers.openai_compatible_provider import OpenAiCompatibleProvider
from app.ai_providers.provider_base import AIRequest, DisabledProvider
from app.ai_providers.provider_types import (
    FREE_WEB_AI,
    MANUAL_REQUIRED,
    NOT_CONFIGURED,
    OK,
    STATUS_DISABLED,
    TASK_GENERAL,
)

REQ = AIRequest(task_type=TASK_GENERAL, prompt="What is the outlook?", system_prompt="Be brief.")


def test_disabled_provider() -> None:
    provider = DisabledProvider()
    assert provider.is_available() is False
    response = provider.generate(REQ)
    assert response.status == STATUS_DISABLED
    assert response.is_ok is False


def test_manual_paste_returns_prompt() -> None:
    provider = ManualPasteProvider()
    assert provider.is_available() is True
    response = provider.generate(REQ)
    assert response.status == MANUAL_REQUIRED
    assert response.manual_prompt == "Be brief.\n\nWhat is the outlook?"
    assert response.text is None


def test_free_web_ai_provider_type() -> None:
    response = FreeWebAiProvider().generate(REQ)
    assert response.provider_type == FREE_WEB_AI
    assert response.status == MANUAL_REQUIRED


def test_openai_compatible_with_injected_call_fn() -> None:
    provider = OpenAiCompatibleProvider(
        enabled=True, api_key="k", call_fn=lambda r: f"answer to: {r.prompt}"
    )
    assert provider.is_available() is True
    response = provider.generate(REQ)
    assert response.status == OK
    assert response.text == "answer to: What is the outlook?"


def test_openai_compatible_not_configured_without_key() -> None:
    provider = OpenAiCompatibleProvider(enabled=True, api_key="")
    assert provider.is_available() is False
    response = provider.generate(REQ)
    assert response.status == NOT_CONFIGURED


def test_provider_disabled_when_not_enabled() -> None:
    provider = OpenAiCompatibleProvider(enabled=False, api_key="k")
    response = provider.generate(REQ)
    assert response.status == STATUS_DISABLED


def test_gemini_and_ollama_with_call_fn() -> None:
    gemini = GeminiProvider(enabled=True, api_key="k", call_fn=lambda r: "gemini-out")
    assert gemini.generate(REQ).text == "gemini-out"

    ollama = OllamaProvider(enabled=True, call_fn=lambda r: "ollama-out")
    assert ollama.generate(REQ).text == "ollama-out"


def test_ollama_not_configured_without_base_url() -> None:
    ollama = OllamaProvider(enabled=True, base_url="")
    assert ollama.is_available() is False
    assert ollama.generate(REQ).status == NOT_CONFIGURED
