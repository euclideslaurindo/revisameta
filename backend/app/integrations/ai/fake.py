"""Fake provider for tests and development: no network, answers scripted by the test.

The CI never calls a real provider (docs/validacao.md 11.2, AI).
"""

from collections import deque
from typing import Any

from pydantic import BaseModel

from app.integrations.ai.base import AIError, parse_structured


class FakeProvider:
    name = "fake"
    model = "fake-1"

    def __init__(self) -> None:
        self.answers: deque[str | AIError] = deque()
        self.calls: list[dict[str, Any]] = []

    def will_answer(self, *answers: str | AIError) -> None:
        self.answers.extend(answers)

    def _next(self, kind: str, system: str, prompt: str) -> str:
        self.calls.append({"kind": kind, "system": system, "prompt": prompt})
        if not self.answers:
            raise AssertionError("FakeProvider called without a scripted answer")
        answer = self.answers.popleft()
        if isinstance(answer, AIError):
            raise answer
        return answer

    async def complete(self, system: str, prompt: str) -> str:
        return self._next("complete", system, prompt)

    async def complete_structured[T: BaseModel](
        self, system: str, prompt: str, schema: type[T]
    ) -> T:
        return parse_structured(self._next("structured", system, prompt), schema)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls.append({"kind": "embed", "texts": texts})
        return [[float(len(t)), 0.0] for t in texts]
