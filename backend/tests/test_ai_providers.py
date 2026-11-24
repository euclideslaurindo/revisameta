"""AI provider layer (stage 7 step 1). No real provider is ever called: the Gemini
adapter talks to an httpx mock transport."""

import json

import httpx
import pytest
from pydantic import BaseModel

from app.integrations.ai import FakeProvider, GeminiProvider, get_ai_provider
from app.integrations.ai.base import (
    AIError,
    AIInvalidOutputError,
    AIQuotaExceededError,
    AIUnavailableError,
)


class Quote(BaseModel):
    quote: str
    page: int


def _gemini(handler: object) -> GeminiProvider:
    return GeminiProvider("test-key", "gemini-test", transport=httpx.MockTransport(handler))  # type: ignore[arg-type]


def _answer(text: str) -> httpx.Response:
    return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": text}]}}]})


async def test_gemini_sends_system_apart_and_key_in_header() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["key"] = request.headers["x-goog-api-key"]
        seen["body"] = json.loads(request.content)
        return _answer('{"quote": "randomised", "page": 3}')

    out = await _gemini(handler).complete_structured("SYSTEM", "PDF TEXT", Quote)
    assert out == Quote(quote="randomised", page=3)
    assert "test-key" not in str(seen["url"]) and seen["key"] == "test-key"
    body = seen["body"]
    assert isinstance(body, dict)
    assert body["systemInstruction"]["parts"][0]["text"] == "SYSTEM"
    assert body["contents"][0]["parts"][0]["text"] == "PDF TEXT"
    assert body["generationConfig"]["responseMimeType"] == "application/json"


async def test_gemini_errors_become_clear_states() -> None:
    with pytest.raises(AIQuotaExceededError):
        await _gemini(lambda r: httpx.Response(429)).complete("s", "p")
    with pytest.raises(AIUnavailableError):
        await _gemini(lambda r: httpx.Response(403)).complete("s", "p")
    with pytest.raises(AIError):
        await _gemini(lambda r: httpx.Response(200, json={"candidates": []})).complete("s", "p")
    # Out-of-schema answers are discarded, never shown.
    with pytest.raises(AIInvalidOutputError):
        await _gemini(lambda r: _answer('{"quote": 1}')).complete_structured("s", "p", Quote)
    with pytest.raises(AIUnavailableError):
        GeminiProvider("", "gemini-test")


async def test_gemini_embeddings() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        n = len(json.loads(request.content)["requests"])
        return httpx.Response(200, json={"embeddings": [{"values": [0.1, 0.2]}] * n})

    assert await _gemini(handler).embed(["a", "b"]) == [[0.1, 0.2], [0.1, 0.2]]


async def test_fake_provider_and_factory(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeProvider()
    fake.will_answer('```json\n{"quote": "x", "page": 1}\n```', AIQuotaExceededError())
    assert (await fake.complete_structured("s", "p", Quote)).page == 1
    with pytest.raises(AIQuotaExceededError):
        await fake.complete("s", "p")
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "ai_provider", "none")
    with pytest.raises(AIUnavailableError):
        get_ai_provider()
    monkeypatch.setattr(get_settings(), "ai_provider", "gemini")
    monkeypatch.setattr(get_settings(), "gemini_api_key", "")
    with pytest.raises(AIUnavailableError):
        get_ai_provider()
