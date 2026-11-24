"""Gemini adapter (free tier first; docs/ia.md 7.15.5).

Plain REST over httpx (already a dependency) instead of the vendor SDK: three calls are
all we need, and keeping vendor code out of the dependency tree keeps the layer
swappable. The key goes in a header (never in the URL, so it does not reach logs) and
must be a key restricted to the Gemini API.

Free-tier facts checked on 2026-11-23 (docs/roteiro.md): prompts may be used to improve
Google products; quotas are per Google project, change without notice and reset at
midnight Pacific time. A 429 is a normal state here: AIQuotaExceededError, never a crash.
"""

import json
from typing import Any

import httpx
from pydantic import BaseModel

from app.integrations.ai.base import (
    AIError,
    AIQuotaExceededError,
    AIUnavailableError,
    parse_structured,
)

BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
TIMEOUT = 60


class GeminiProvider:
    name = "gemini"

    def __init__(
        self,
        api_key: str,
        model: str,
        embed_model: str = "text-embedding-004",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not api_key:
            raise AIUnavailableError("no Gemini key configured")
        self.model = model
        self._key = api_key
        self._embed_model = embed_model
        self._transport = transport

    async def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        headers = {"x-goog-api-key": self._key, "Content-Type": "application/json"}
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT, transport=self._transport) as client:
                response = await client.post(f"{BASE_URL}/{path}", json=body, headers=headers)
        except httpx.HTTPError as error:
            raise AIError(f"Gemini unreachable: {type(error).__name__}") from error
        if response.status_code == 429:
            raise AIQuotaExceededError("Gemini quota exceeded")
        if response.status_code in (401, 403):
            raise AIUnavailableError("Gemini key rejected")
        if response.status_code >= 400:
            raise AIError(f"Gemini error {response.status_code}")
        data: dict[str, Any] = response.json()
        return data

    @staticmethod
    def _text(data: dict[str, Any]) -> str:
        try:
            parts = data["candidates"][0]["content"]["parts"]
        except (KeyError, IndexError, TypeError) as error:
            raise AIError("Gemini answer without text (blocked or empty)") from error
        return "".join(p.get("text", "") for p in parts)

    def _body(self, system: str, prompt: str) -> dict[str, Any]:
        # System instructions stay apart from the content (7.15.3, rule 6).
        return {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.2},
        }

    async def complete(self, system: str, prompt: str) -> str:
        data = await self._post(f"models/{self.model}:generateContent", self._body(system, prompt))
        return self._text(data)

    async def complete_structured[T: BaseModel](
        self, system: str, prompt: str, schema: type[T]
    ) -> T:
        body = self._body(system, prompt)
        body["generationConfig"] |= {
            "responseMimeType": "application/json",
            "responseJsonSchema": schema.model_json_schema(),
        }
        data = await self._post(f"models/{self.model}:generateContent", body)
        return parse_structured(self._text(data), schema)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        body = {
            "requests": [
                {"model": f"models/{self._embed_model}", "content": {"parts": [{"text": t}]}}
                for t in texts
            ]
        }
        data = await self._post(f"models/{self._embed_model}:batchEmbedContents", body)
        try:
            return [e["values"] for e in data["embeddings"]]
        except (KeyError, TypeError) as error:
            raise AIError(f"Gemini embeddings malformed: {json.dumps(data)[:200]}") from error
