from app.ai_providers.gemini_provider import GeminiProvider
from app.ai_providers.manual_paste_provider import ManualPasteProvider
from app.ai_providers.provider_base import DisabledProvider
from app.ai_providers.provider_limit_tracker import ProviderLimitTracker
from app.ai_providers.provider_manager import AIProviderManager
from app.ai_providers.provider_registry import ProviderRegistry
from app.ai_providers.provider_router import ProviderRouter
from app.ai_providers.provider_types import (
    DISABLED,
    GEMINI,
    MANUAL_PASTE,
    MANUAL_REQUIRED,
    OK,
    STATUS_DISABLED,
    TASK_GENERAL,
    TASK_OPTION_TEXT_READER,
)
from app.core.config import AppSettings


def _registry(gemini):
    return ProviderRegistry(
        {
            DISABLED: DisabledProvider(),
            MANUAL_PASTE: ManualPasteProvider(),
            GEMINI: gemini,
        }
    )


def test_router_selects_active_then_fallback() -> None:
    router = ProviderRouter(active_type=GEMINI, fallback_type=MANUAL_PASTE)
    assert router.select(TASK_GENERAL) == [GEMINI, MANUAL_PASTE]


def test_router_task_override_for_option_text_reader() -> None:
    router = ProviderRouter(
        active_type=GEMINI,
        fallback_type=DISABLED,
        task_overrides={TASK_OPTION_TEXT_READER: MANUAL_PASTE},
    )
    # The override replaces the active provider for this task; fallback follows.
    assert router.select(TASK_OPTION_TEXT_READER) == [MANUAL_PASTE, DISABLED]
    assert router.select(TASK_GENERAL) == [GEMINI, DISABLED]


def test_manager_default_is_disabled() -> None:
    manager = AIProviderManager(settings=AppSettings())
    response = manager.generate(TASK_GENERAL, "hello")
    assert response.status == STATUS_DISABLED


def test_manager_uses_active_provider() -> None:
    gemini = GeminiProvider(enabled=True, api_key="k", call_fn=lambda r: "out")
    manager = AIProviderManager(
        settings=AppSettings(),
        registry=_registry(gemini),
        active_type=GEMINI,
        fallback_type=MANUAL_PASTE,
    )
    response = manager.generate(TASK_GENERAL, "hello")
    assert response.status == OK
    assert response.text == "out"


def test_manager_falls_back_when_active_unavailable() -> None:
    unconfigured = GeminiProvider(enabled=True)  # no key, no call_fn -> unavailable
    manager = AIProviderManager(
        settings=AppSettings(),
        registry=_registry(unconfigured),
        active_type=GEMINI,
        fallback_type=MANUAL_PASTE,
    )
    response = manager.generate(TASK_GENERAL, "hello")
    assert response.status == MANUAL_REQUIRED  # fell back to manual paste


def test_manager_respects_usage_limit() -> None:
    gemini = GeminiProvider(enabled=True, api_key="k", call_fn=lambda r: "out")
    manager = AIProviderManager(
        settings=AppSettings(),
        registry=_registry(gemini),
        active_type=GEMINI,
        fallback_type=MANUAL_PASTE,
        limit_tracker=ProviderLimitTracker({GEMINI: 1}),
    )
    first = manager.generate(TASK_GENERAL, "1")
    second = manager.generate(TASK_GENERAL, "2")
    assert first.status == OK
    # Limit reached -> falls back to manual paste.
    assert second.status == MANUAL_REQUIRED


def test_read_option_text_routes_to_active() -> None:
    gemini = GeminiProvider(enabled=True, api_key="k", call_fn=lambda r: f"read: {r.prompt}")
    manager = AIProviderManager(
        settings=AppSettings(),
        registry=_registry(gemini),
        active_type=GEMINI,
        fallback_type=MANUAL_PASTE,
    )
    response = manager.read_option_text("AAPL 200C")
    assert response.status == OK
    assert response.task_type == TASK_OPTION_TEXT_READER
    assert response.text == "read: AAPL 200C"


def test_manager_status() -> None:
    manager = AIProviderManager(settings=AppSettings())
    status = manager.get_status()
    assert status["active_provider"] == "DISABLED"
    assert status["ai_enabled"] is False
    assert "providers" in status and "health" in status
