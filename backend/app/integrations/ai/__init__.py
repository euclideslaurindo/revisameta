"""AI provider layer. `get_ai_provider()` is the only entry point (a FastAPI dependency)."""

from app.core.config import get_settings
from app.integrations.ai.base import AIProvider, AIUnavailableError
from app.integrations.ai.fake import FakeProvider
from app.integrations.ai.gemini import GeminiProvider

_fake = FakeProvider()


def get_ai_provider() -> AIProvider:
    settings = get_settings()
    if settings.ai_provider == "gemini":
        return GeminiProvider(settings.gemini_api_key, settings.ai_model)
    if settings.ai_provider == "fake":
        return _fake
    raise AIUnavailableError("AI provider not configured")


__all__ = ["AIProvider", "FakeProvider", "GeminiProvider", "get_ai_provider"]
